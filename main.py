import asyncio
import base64
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api.all import logger
from astrbot.core.message.components import Node, Nodes, Image, Plain

API_URL = "https://api.lolicon.app/setu/v2"

VALID_SIZES = ("original", "regular", "small", "thumb", "mini")


@register("astrbot_plugin_setu", "wjy", "基于 Lolicon API 的随机动漫图片插件", "1.0.0")
class SetuPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.plugin_config = config

    def _get_conf(self, key: str, default=None):
        try:
            if self.plugin_config is None:
                logger.warning(f"[SetuPlugin] plugin_config 为 None，使用默认值: {key}={default}")
                return default
            if hasattr(self.plugin_config, 'get'):
                value = self.plugin_config.get(key, default)
            elif hasattr(self.plugin_config, key):
                value = getattr(self.plugin_config, key)
            else:
                value = default
            logger.debug(f"[SetuPlugin] 原始配置: {key}={value}({type(value).__name__})")
            if key in ("r18", "use_forward", "filter_ai", "auto_recall", "forward_fallback"):
                if isinstance(value, str):
                    value = value.lower() in ("true", "1", "yes", "on")
                value = bool(value)
            elif key == "max_num":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    value = default
                if value < 1:
                    value = 1
                if value > 20:
                    value = 20
            elif key == "recall_time":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    value = default
                if value < 1:
                    value = 1
                if value > 120:
                    value = 120
            elif key == "send_interval":
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    value = default
                if value < 0.1:
                    value = 0.1
                if value > 10:
                    value = 10
            elif key == "send_retry":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    value = default
                if value < 0:
                    value = 0
                if value > 5:
                    value = 5
            elif key == "size":
                if value not in VALID_SIZES:
                    value = "regular"
            return value
        except Exception as e:
            logger.error(f"[SetuPlugin] 获取配置失败: {e}")
            return default

    async def _recall_message(self, bot, message_id, delay):
        """定时撤回消息"""
        await asyncio.sleep(delay)
        try:
            await bot.call_action("delete_msg", message_id=message_id)
            logger.info(f"[SetuPlugin] 已撤回消息: {message_id}")
        except Exception as e:
            logger.error(f"[SetuPlugin] 撤回消息失败: {e}")

    async def _send_forward_once(self, bot, is_group, session_id, payload, routing_params):
        """单次发送合并转发，返回 message_id，失败返回 None"""
        try:
            if is_group:
                payload["group_id"] = session_id
                payload.update(routing_params)
                result = await bot.call_action("send_group_forward_msg", **payload)
            else:
                payload["user_id"] = session_id
                payload.update(routing_params)
                result = await bot.call_action("send_private_forward_msg", **payload)
            if isinstance(result, dict) and result.get("message_id"):
                return result["message_id"]
        except Exception as e:
            logger.error(f"[SetuPlugin] 合并转发发送失败: {e}")
        return None

    async def _send_image_once(self, bot, is_group, session_id, b64_str, routing_params):
        """单次发送单张图片，返回 (message_id, is_timeout)，失败返回 (None, is_timeout)"""
        try:
            msg = [{"type": "image", "data": {"file": f"base64://{b64_str}"}}]
            if is_group:
                result = await bot.call_action("send_group_msg",
                                               group_id=int(session_id),
                                               message=msg,
                                               **routing_params)
            else:
                result = await bot.call_action("send_private_msg",
                                               user_id=int(session_id),
                                               message=msg,
                                               **routing_params)
            if isinstance(result, dict) and result.get("message_id"):
                return result["message_id"], False
        except Exception as e:
            err_str = str(e)
            is_timeout = "Timeout" in err_str or "1200" in err_str
            if is_timeout:
                logger.warning(f"[SetuPlugin] 图片发送超时（QQ 风控），跳过重试")
            else:
                logger.error(f"[SetuPlugin] 图片发送失败: {e}")
            return None, is_timeout
        return None, False

    async def _send_with_bot(self, event, is_forward, nodes, img_b64_list, recall_time, enable_recall=False):
        """通过 bot API 发送，逐张独立发送，部分失败不影响其他。返回发送结果列表 [(index, True/False)]"""
        bot = getattr(event, 'bot', None)
        if not bot:
            return []

        is_group = bool(event.get_group_id())
        session_id = event.get_group_id() if is_group else event.get_sender_id()
        if not session_id or not str(session_id).isdigit():
            return []
        session_id = str(session_id)

        raw_message = getattr(event.message_obj, 'raw_message', None)
        routing_params = {}
        if raw_message and hasattr(raw_message, 'get'):
            self_id = raw_message.get("self_id")
            if self_id:
                routing_params["self_id"] = self_id

        results = []
        send_interval = self._get_conf("send_interval", 1.0)
        send_retry = self._get_conf("send_retry", 2)

        if is_forward and nodes:
            payload = await nodes.to_dict()
            mid = await self._send_forward_once(bot, is_group, session_id, payload, routing_params)
            if mid:
                if enable_recall:
                    asyncio.create_task(self._recall_message(bot, mid, recall_time))
                results.append((0, True))
            else:
                results.append((0, False))
        else:
            for idx, b64 in enumerate(img_b64_list):
                mid = None
                for attempt in range(send_retry + 1):
                    mid, is_timeout = await self._send_image_once(bot, is_group, session_id, b64, routing_params)
                    if mid:
                        break
                    # 超时不重试（浪费时间），其他错误才重试
                    if is_timeout or attempt >= send_retry:
                        break
                    backoff = min(2 ** attempt, 5)
                    logger.info(f"[SetuPlugin] 图片 {idx+1} 发送失败，{backoff} 秒后重试 ({attempt+1}/{send_retry})")
                    await asyncio.sleep(backoff)

                if mid:
                    if enable_recall:
                        asyncio.create_task(self._recall_message(bot, mid, recall_time))
                    results.append((idx, True))
                else:
                    results.append((idx, False))

                if idx < len(img_b64_list) - 1:
                    await asyncio.sleep(send_interval)

        return results

    @filter.command("p")
    async def setu(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if args and args[0].lower() == "p":
            args = args[1:]

        num = None
        tags = []
        cmd_r18 = None

        for arg in args:
            if arg.isdigit():
                if num is None:
                    num = int(arg)
                else:
                    tags.append(arg)
            elif arg.lower() == "r18":
                cmd_r18 = True
            elif arg.lower().startswith("r18="):
                try:
                    cmd_r18 = int(arg.split("=")[1]) != 0
                except (ValueError, IndexError):
                    pass
            else:
                tags.append(arg)

        r18 = self._get_conf("r18", False)
        if cmd_r18 is not None:
            if r18:
                r18 = cmd_r18
            else:
                logger.info("[SetuPlugin] 配置未开启 R18，忽略命令中的 r18 参数")
        max_num = self._get_conf("max_num", 3)
        proxy = self._get_conf("proxy", "i.pixiv.re")
        size = self._get_conf("size", "regular")
        filter_ai = self._get_conf("filter_ai", False)
        logger.info(f"[SetuPlugin] 最终配置: r18={r18}, max_num={max_num}, size={size}, filter_ai={filter_ai}, tags={tags}")

        if num is None:
            num = 1
        if num > max_num:
            num = max_num
        if num < 1:
            num = 1

        payload = {
            "r18": 1 if r18 else 0,
            "proxy": proxy,
            "size": [size]
        }

        if tags:
            payload["tag"] = tags

        try:
            connector = aiohttp.TCPConnector(limit_per_host=10, ssl=False)
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
                result_list = []
                max_retries = 3 if filter_ai else 1

                for attempt in range(max_retries):
                    need = num - len(result_list)
                    if need <= 0:
                        break

                    req_num = min(need * 3 if filter_ai else need, 20)
                    payload["num"] = req_num
                    logger.info(f"[SetuPlugin] 第 {attempt + 1} 次请求，需要 {need} 张，请求 {req_num} 张")

                    logger.info(f"[SetuPlugin] 请求参数: {payload}")
                    async with session.post(API_URL, json=payload) as resp:
                        logger.info(f"[SetuPlugin] 响应状态码: {resp.status}")
                        if resp.status != 200:
                            error_text = await resp.text()
                            logger.error(f"[SetuPlugin] 请求失败，响应内容: {error_text}")
                            if not result_list:
                                event.set_result(MessageEventResult().message(f"请求失败，状态码：{resp.status}"))
                                event.should_call_llm(True)
                                return
                            break

                        try:
                            data = await resp.json(content_type=None)
                        except Exception as e:
                            logger.error(f"[SetuPlugin] JSON 解析失败: {e}")
                            if not result_list:
                                event.set_result(MessageEventResult().message("API 响应解析失败，可能被 DNS 污染，请稍后重试~"))
                                event.should_call_llm(True)
                                return
                            break

                        logger.debug(f"[SetuPlugin] 响应数据类型: {type(data).__name__}")
                        logger.debug(f"[SetuPlugin] 响应数据: {data}")

                        if isinstance(data, dict):
                            if data.get("error"):
                                logger.error(f"[SetuPlugin] API 错误: {data['error']}")
                                if not result_list:
                                    event.set_result(MessageEventResult().message(f"API 错误：{data['error']}"))
                                    event.should_call_llm(True)
                                    return
                                break
                            batch = data.get("data", [])
                        elif isinstance(data, list):
                            batch = data
                        else:
                            batch = []

                        logger.info(f"[SetuPlugin] batch 长度: {len(batch)}")

                        original_batch_len = len(batch)

                        if filter_ai:
                            before = len(batch)
                            batch = [item for item in batch if item.get("aiType", 0) == 0]
                            logger.info(f"[SetuPlugin] AI 过滤: {before} -> {len(batch)}")

                        result_list.extend(batch)

                        if original_batch_len < req_num:
                            break

                # 截取需要的数量
                result_list = result_list[:num]

                if not result_list:
                    event.set_result(MessageEventResult().message("没有找到符合条件的图片~"))
                    event.should_call_llm(True)
                    return

                results = []
                for item in result_list:
                    urls = item.get("urls", {})
                    img_url = urls.get(size, urls.get("original", ""))
                    if img_url:
                        results.append(img_url)
                    else:
                        pid = item.get("pid", "")
                        logger.warning(f"[SetuPlugin] 图片链接获取失败（PID: {pid}）")

                if not results:
                    event.set_result(MessageEventResult().message("所有图片链接获取失败~"))
                    event.should_call_llm(True)
                    return

                use_forward = self._get_conf("use_forward", False)
                auto_recall = self._get_conf("auto_recall", False)
                recall_time = self._get_conf("recall_time", 60)
                forward_fallback = self._get_conf("forward_fallback", True)

                # 下载图片为 base64
                async def _download_image(session, url):
                    try:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                b64_str = base64.b64encode(data).decode()
                                logger.info(f"[SetuPlugin] 图片下载成功: {len(data)} bytes")
                                return b64_str
                    except Exception as e:
                        logger.error(f"[SetuPlugin] 下载图片失败: {url} - {e}")
                    return None

                # 下载所有图片为 base64
                img_b64_list = []
                for img_url in results:
                    b64 = await _download_image(session, img_url)
                    if b64:
                        img_b64_list.append(b64)
                    else:
                        logger.warning(f"[SetuPlugin] 图片下载失败，跳过: {img_url}")

                if not img_b64_list:
                    event.set_result(MessageEventResult().message("图片下载失败，请稍后重试~"))
                    event.should_call_llm(True)
                    return

                # 普通图片发送逻辑（封装为函数以便回退复用）
                async def _send_normal_images():
                    # 通过 bot API 逐张独立发送（含重试）
                    sent_results = await self._send_with_bot(event, False, None, img_b64_list, recall_time, enable_recall=auto_recall)

                    # bot API 不可用，走 event.send
                    if not sent_results:
                        for b64 in img_b64_list:
                            try:
                                await event.send(MessageChain(chain=[Image.fromBase64(b64)]))
                                await asyncio.sleep(0.5)
                            except Exception as e:
                                logger.error(f"[SetuPlugin] 图片发送失败: {e}")
                        event.set_result(MessageEventResult().message("图片发送失败，可能被风控~"))
                        event.should_call_llm(True)
                        return

                    failed_indices = [idx for idx, success in sent_results if not success]
                    success_count = len(sent_results) - len(failed_indices)

                    if not failed_indices:
                        event.should_call_llm(True)
                        return

                    # 全部失败，不再尝试 event.send（同样会超时）
                    if success_count == 0:
                        event.set_result(MessageEventResult().message("图片发送失败，可能被风控，请稍后重试~"))
                        event.should_call_llm(True)
                        return

                    # 部分失败，尝试 event.send 补发
                    for idx in failed_indices:
                        if idx < len(img_b64_list):
                            try:
                                await event.send(MessageChain(chain=[Image.fromBase64(img_b64_list[idx])]))
                                await asyncio.sleep(0.5)
                            except Exception as e:
                                logger.error(f"[SetuPlugin] 图片 {idx+1} 补发失败: {e}")

                    event.set_result(MessageEventResult().message(f"部分图片发送失败（成功 {success_count}/{len(img_b64_list)}），可能被风控~"))
                    event.should_call_llm(True)

                if use_forward:
                    self_id = event.get_self_id() or "0"
                    nodes = []
                    for idx, item in enumerate(result_list):
                        title = item.get("title", "未知标题")
                        author = item.get("author", "未知作者")
                        pid = item.get("pid", "")
                        if idx < len(img_b64_list):
                            content = [
                                Plain(f"标题: {title}\n作者: {author}\nPID: {pid}"),
                                Image.fromBase64(img_b64_list[idx])
                            ]
                            node = Node(content=content, name="涩图Bot", uin=self_id)
                            nodes.append(node)
                    if nodes:
                        forward_nodes = Nodes(nodes=nodes)
                        # 通过 bot API 直接发送合并转发
                        sent_results = await self._send_with_bot(event, True, forward_nodes, None, recall_time, enable_recall=auto_recall)
                        if any(success for _, success in sent_results):
                            event.should_call_llm(True)
                            return
                        # bot API 失败，尝试 event.send
                        try:
                            await event.send(MessageChain(chain=[forward_nodes]))
                            event.should_call_llm(True)
                            return
                        except Exception as e:
                            logger.error(f"[SetuPlugin] 合并转发发送失败: {e}")
                        # 合并转发完全失败
                        if forward_fallback:
                            logger.info("[SetuPlugin] 合并转发失败，回退为普通图片发送")
                            await _send_normal_images()
                            return
                        else:
                            event.set_result(MessageEventResult().message("合并转发发送失败，可能被风控，请稍后重试或关闭合并转发配置~"))
                            event.should_call_llm(True)
                            return
                    else:
                        event.set_result(MessageEventResult().message("图片构建失败~"))
                        event.should_call_llm(True)
                else:
                    await _send_normal_images()
                    return

        except aiohttp.ClientError as e:
            logger.error(f"[SetuPlugin] 网络请求错误: {e}")
            event.set_result(MessageEventResult().message("网络请求出错，请稍后重试~"))
            event.should_call_llm(True)
        except Exception as e:
            logger.error(f"[SetuPlugin] 未知错误: {e}")
            event.set_result(MessageEventResult().message("发生未知错误，请检查日志~"))
            event.should_call_llm(True)
