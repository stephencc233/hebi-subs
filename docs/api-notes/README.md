# 接口实测记录（P2）

| 文件 | 内容 |
|---|---|
| `mp-local-env.md` | （P0）本机 MP 环境：版本、Python、配置与开关、日志、插件目录、端口 |
| `mp-v3-plugin.md` | （P0）MP V3 插件开发要点：目录与索引、生命周期、整理完成事件字段、页面/API、本地开发与热重载 |
| `assrt.md` | （P2-B）ASSRT API：search / detail / quota 实测字段 → D014 映射、cnt / pos 分页、配额（本账号 5 次/分钟）、下载链接时效、与 SubHD 对比 |
| `subhd.md` | SubHD：搜索页、详情页字段（下载量、制作组、来源类型）、下载流程、验证码触发条件 |
| `jellyfin-subtitle-naming.md` | （P2-D）Jellyfin 12.1 外挂字幕命名识别实测：匹配与解析规则（源码 v12.1）、语言码与自动选择、两份双语如何区分（F6.6 方案对比）、子文件夹与忽略规则（F6.7）、缺 `[Script Info]` 的 ASS 被静默跳过 |
| `archive-tools.md` | （P2-C）Windows 原生解包工具链（7-Zip / tar.exe / py7zr）能力矩阵、zip 文件名回转、字幕包样本统计、manifest 字段、D015 定稿建议 |

每条记录写：日期、请求、关键返回字段、结论、对设计的影响。
