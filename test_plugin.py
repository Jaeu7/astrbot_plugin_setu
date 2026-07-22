import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from astrbot.api.star import Context
from main import SetuPlugin, API_URL


class MockConfig:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def get(self, key, default=None):
        return getattr(self, key, default)


class MockContext:
    def __init__(self):
        pass


async def test_config_read():
    print("\n=== 测试配置读取 ===")
    config = MockConfig(r18=False, max_num=3, proxy="i.pixiv.re", size="regular", use_forward=False, filter_ai=False)
    context = MockContext()
    plugin = SetuPlugin(context, config)
    
    r18 = plugin._get_conf("r18", False)
    max_num = plugin._get_conf("max_num", 3)
    proxy = plugin._get_conf("proxy", "i.pixiv.re")
    size = plugin._get_conf("size", "regular")
    use_forward = plugin._get_conf("use_forward", False)
    filter_ai = plugin._get_conf("filter_ai", False)
    
    assert r18 == False, f"r18 配置错误: {r18}"
    assert max_num == 3, f"max_num 配置错误: {max_num}"
    assert proxy == "i.pixiv.re", f"proxy 配置错误: {proxy}"
    assert size == "regular", f"size 配置错误: {size}"
    assert use_forward == False, f"use_forward 配置错误: {use_forward}"
    assert filter_ai == False, f"filter_ai 配置错误: {filter_ai}"
    
    print("✓ 配置读取测试通过")


async def test_api_request():
    print("\n=== 测试 API 请求 ===")
    import aiohttp
    
    config = MockConfig(r18=False, max_num=1, proxy="i.pixiv.re", size="regular", use_forward=False, filter_ai=False)
    context = MockContext()
    plugin = SetuPlugin(context, config)
    
    payload = {
        "r18": 0,
        "num": 1,
        "proxy": "i.pixiv.re",
        "size": ["regular"]
    }
    
    try:
        connector = aiohttp.TCPConnector(limit_per_host=10)
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
            async with session.post(API_URL, json=payload) as resp:
                print(f"状态码: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"错误信息: {data.get('error', '')}")
                    print(f"返回数量: {len(data.get('data', []))}")
                    if data.get("data"):
                        item = data["data"][0]
                        print(f"PID: {item.get('pid')}")
                        print(f"标题: {item.get('title')}")
                        print(f"作者: {item.get('author')}")
                        print(f"AI类型: {item.get('aiType')}")
                        print(f"图片URL: {item.get('urls', {}).get('regular')}")
                    print("✓ API 请求测试通过")
                else:
                    print(f"✗ API 请求失败，状态码: {resp.status}")
    except Exception as e:
        print(f"✗ API 请求异常: {e}")


async def test_api_with_filter_ai():
    print("\n=== 测试过滤 AI 作品 ===")
    import aiohttp
    
    payload = {
        "r18": 0,
        "num": 3,
        "proxy": "i.pixiv.re",
        "size": ["regular"],
        "aiType": 0
    }
    
    try:
        connector = aiohttp.TCPConnector(limit_per_host=10)
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
            async with session.post(API_URL, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result_list = data.get("data", [])
                    print(f"返回数量: {len(result_list)}")
                    ai_count = sum(1 for item in result_list if item.get("aiType") != 0)
                    print(f"AI作品数量: {ai_count}")
                    if ai_count == 0:
                        print("✓ 过滤 AI 作品测试通过")
                    else:
                        print("✗ 仍有 AI 作品未被过滤")
                else:
                    print(f"✗ API 请求失败，状态码: {resp.status}")
    except Exception as e:
        print(f"✗ API 请求异常: {e}")


async def test_api_with_tags():
    print("\n=== 测试标签搜索 ===")
    import aiohttp
    
    payload = {
        "r18": 0,
        "num": 1,
        "proxy": "i.pixiv.re",
        "size": ["regular"],
        "tag": ["萝莉"]
    }
    
    try:
        connector = aiohttp.TCPConnector(limit_per_host=10)
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
            async with session.post(API_URL, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result_list = data.get("data", [])
                    print(f"返回数量: {len(result_list)}")
                    if result_list:
                        item = result_list[0]
                        tags = item.get("tags", [])
                        print(f"标签: {tags}")
                        print("✓ 标签搜索测试通过")
                    else:
                        print("✗ 未找到符合条件的图片")
                else:
                    print(f"✗ API 请求失败，状态码: {resp.status}")
    except Exception as e:
        print(f"✗ API 请求异常: {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("AstrBot Setu Plugin 测试")
    print("=" * 50)
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_config_read())
    loop.run_until_complete(test_api_request())
    loop.run_until_complete(test_api_with_filter_ai())
    loop.run_until_complete(test_api_with_tags())
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)
