import aiohttp
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.all import logger
from astrbot.core.message.components import Node, Nodes, Image, Plain

API_URL = "https://api.lolicon.app/setu/v2"


@register("astrbot_plugin_setu", "wjy", "基于 Lolicon API 的随机动漫图片插件", "1.0.0")
class SetuPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.plugin_config = config

    def _get_conf(self, key: str, default=None):
        try:
            if self.plugin_config is None:
                logger.warning(f"[SetuPlugin] plugin_config is None")
                return default
            logger.info(f"[SetuPlugin] plugin_config type: {type(self.plugin_config).__name__}")
            if hasattr(self.plugin_config, 'get'):
                value = self.plugin_config.get(key, default)
            elif hasattr(self.plugin_config, key):
                value = getattr(self.plugin_config, key)
            else:
                value = default
            logger.info(f"[SetuPlugin] 获取配置: {key}={value}({type(value).__name__})")
            if key in ("r18", "use_forward", "filter_ai"):
                if isinstance(value, str):
                    value = value.lower() in ("true", "1", "yes", "on")
                value = bool(value)
            elif key == "max_num":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    value = default
            return value
        except Exception as e:
            logger.error(f"[SetuPlugin] 获取配置失败: {e}")
            return default

    @filter.command("p")
    async def setu(self, event: AstrMessageEvent):
        logger.info(f"[SetuPlugin] 原始消息: {event.message_str}")
        args = event.message_str.strip().split()
        logger.info(f"[SetuPlugin] 分割后参数: {args}")
        if args and args[0] in ("/p", "/P", "p", "P"):
            args = args[1:]
        logger.info(f"[SetuPlugin] 处理后参数: {args}")

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
            r18 = cmd_r18
        max_num = self._get_conf("max_num", 3)
        proxy = self._get_conf("proxy", "i.pixiv.re")
        size = self._get_conf("size", "regular")
        filter_ai = self._get_conf("filter_ai", False)
        logger.info(f"[SetuPlugin] 配置: r18={r18}, max_num={max_num}, proxy={proxy}, size={size}, filter_ai={filter_ai}")

        if num is None:
            num = 1
        if num > max_num:
            num = max_num
        if num < 1:
            num = 1
        if num > 20:
            num = 20

        payload = {
            "r18": 1 if r18 else 0,
            "num": num,
            "proxy": proxy,
            "size": [size]
        }

        if tags:
            payload["tag"] = tags
        
        if filter_ai:
            payload["aiType"] = 0

        logger.info(f"[SetuPlugin] 请求体: {payload}")

        try:
            connector = aiohttp.TCPConnector(limit_per_host=10)
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
                async with session.post(API_URL, json=payload) as resp:
                    logger.info(f"[SetuPlugin] 响应状态码: {resp.status}")
                    if resp.status != 200:
                        event.set_result(MessageEventResult().message(f"请求失败，状态码：{resp.status}"))
                        return

                    data = await resp.json()
                    logger.info(f"[SetuPlugin] 响应数据: {data}")

                    if data.get("error"):
                        event.set_result(MessageEventResult().message(f"API 错误：{data['error']}"))
                        return

                    if isinstance(data, dict):
                        result_list = data.get("data", [])
                    elif isinstance(data, list):
                        result_list = data
                    else:
                        result_list = []
                    logger.info(f"[SetuPlugin] 结果数量: {len(result_list)}")

                    if not result_list:
                        event.set_result(MessageEventResult().message("没有找到符合条件的图片~"))
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
                        return

                    use_forward = self._get_conf("use_forward", False)
                    logger.info(f"[SetuPlugin] use_forward={use_forward}, 结果数量={len(result_list)}")
                    if use_forward:
                        nodes = []
                        for item in result_list:
                            title = item.get("title", "未知标题")
                            author = item.get("author", "未知作者")
                            pid = item.get("pid", "")
                            urls = item.get("urls", {})
                            img_url = urls.get(size, urls.get("original", ""))
                            if img_url:
                                content = [
                                    Plain(f"标题: {title}\n作者: {author}\nPID: {pid}"),
                                    Image.fromURL(img_url)
                                ]
                                node = Node(content=content, name="涩图Bot", uin="0")
                                nodes.append(node)
                                logger.info(f"[SetuPlugin] 构建节点: PID={pid}, title={title}")
                        logger.info(f"[SetuPlugin] 节点总数: {len(nodes)}")
                        if nodes:
                            result = MessageEventResult()
                            nodes_comp = Nodes(nodes=nodes)
                            result.chain.append(nodes_comp)
                            logger.info(f"[SetuPlugin] 发送合并转发消息，节点数: {len(nodes)}")
                            event.set_result(result)
                        else:
                            event.set_result(MessageEventResult().message("图片构建失败~"))
                    else:
                        result = MessageEventResult()
                        for img_url in results:
                            result.url_image(img_url)
                        logger.info(f"[SetuPlugin] 发送普通图片，数量: {len(results)}")
                        event.set_result(result)

        except aiohttp.ClientError as e:
            logger.error(f"[SetuPlugin] 网络请求错误: {e}")
            event.set_result(MessageEventResult().message("网络请求出错，请稍后重试~"))
        except Exception as e:
            logger.error(f"[SetuPlugin] 未知错误: {e}")
            event.set_result(MessageEventResult().message("发生未知错误，请检查日志~"))