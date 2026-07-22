# astrbot_plugin_setu

基于 [Lolicon API](https://docs.api.lolicon.app/) 的随机动漫图片插件。

## 使用方法

| 命令 | 说明 |
|------|------|
| `/p` | 获取 1 张随机图片 |
| `/p 2` | 获取 2 张随机图片 |
| `/p r18` | 获取 R18 图片（需配置开启） |
| `/p 2 r18` | 获取 2 张 R18 图片 |
| `/p 萝莉 白丝` | 按标签搜索（多个标签为 AND 关系） |
| `/p 3 萝莉 白丝` | 按标签搜索并获取 3 张 |
| `/p r18 萝莉` | R18 模式下按标签搜索 |

## 配置项

在 AstrBot 管理后台 → 插件配置中修改：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `r18` | bool | `false` | 是否开启 R18 内容 |
| `max_num` | int | `3` | 单次最多返回图片数量（1-20） |
| `proxy` | string | `i.pixiv.re` | 图片代理地址 |
| `size` | string | `regular` | 图片规格，可选 `original` / `regular` / `small` / `thumb` / `mini` |
| `use_forward` | bool | `false` | 是否以聊天记录形式发送图片（合并转发），仅部分平台支持 |
| `filter_ai` | bool | `false` | 是否过滤 AI 生成的作品，开启后仅返回非 AI 图片 |
| `auto_recall` | bool | `false` | 是否自动撤回发送的图片（仅 QQ 平台有效） |
| `recall_time` | int | `60` | 自动撤回时间（秒），QQ 限制最长 120 秒 |
| `forward_fallback` | bool | `true` | 合并转发失败时是否回退为普通图片发送，关闭则发送报错信息 |
| `send_interval` | float | `1.0` | 发送图片之间的间隔（秒），逐张发送时每张图片之间的最小间隔 |
| `send_retry` | int | `2` | 发送失败后的重试次数，采用指数退避（0-5） |

## 注意事项

- 本插件所有图片均来自 Pixiv，版权归原作者所有
- 请合理使用，避免高频调用
- R18 功能需在配置中手动开启，请遵守相关法律法规
- `use_forward`（聊天记录形式）仅在支持合并转发的平台生效（如 QQ）
- `auto_recall`（自动撤回）仅支持 QQ 平台（aiocqhttp），其他平台会自动回退为普通发送
- 多张图片默认逐张发送以避免 QQ 多图发送超时

## 仓库

- [GitHub](https://github.com/Jaeu7/astrbot_plugin_setu)

## 鸣谢

- [Lolicon API](https://docs.api.lolicon.app/)
