"""
合璧字幕 HebiSubs · MoviePilot V3 插件入口

用途：
    插件主类所在文件。当前为 P0 冒烟测试用的最小空插件，只验证本机 MP 能从本地插件源
    识别、安装、启用本插件，并在日志中打印一行加载成功信息；不含任何字幕业务逻辑。

适用情况：
    MoviePilot V3（system_version >= 3.0.0），Vuetify JSON 渲染模式（宿主默认，无需前端构建）。

如何使用：
    1. MP 的 app.env 中设置 PLUGIN_LOCAL_REPO_PATHS 指向本仓库根目录（package.v3.json 所在处）；
    2. 重启 MP 后在「插件市场」安装「合璧字幕」，在配置页打开「启用插件」并保存；
    3. 在 MP 日志中搜索「合璧字幕」查看加载信息。

依赖的工具及作用：
    - app.sdk.plugin._PluginBase：MP V3 插件基类，规定生命周期方法，并提供 get_data_path() 等工具方法；
    - app.sdk.logging.logger：MP 宿主日志记录器，写入 MP 主日志与本插件日志。
    无第三方 Python 依赖，因此不需要 pyproject.toml。
"""

from typing import Any, Dict, List, Optional, Tuple

# MP V3 稳定 SDK 入口（新插件禁止使用 app.core.* / app.helper.* 等旧路径）
from app.sdk.logging import logger
from app.sdk.plugin import _PluginBase


class HebiSubs(_PluginBase):
    """合璧字幕主类：类名即插件 ID，必须与 package.v3.json 的键、目录名（小写）对应。"""

    # ---- 插件元数据（宿主加载器读取；version 必须与 package.v3.json 一致）----
    plugin_name = "合璧字幕"
    plugin_desc = "从 SubHD 与 ASSRT 获取字幕，在影片同目录落盘「简中+外语」双语字幕，无双语时自动合成。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/chinesesubfinder.png"
    plugin_version = "0.0.1"
    plugin_author = "stephencc233"
    author_url = "https://github.com/stephencc233"
    plugin_config_prefix = "hebisubs_"
    plugin_order = 50
    auth_level = 1

    # ---- 运行状态 ----
    _enabled: bool = False

    def init_plugin(self, config: Optional[Dict[str, Any]] = None) -> None:
        """加载、保存配置、重载时由宿主调用；可重复调用，只读取配置并打印加载信息。"""
        plugin_config = config or {}
        self._enabled = bool(plugin_config.get("enabled", False))

        # get_data_path()：宿主分配的插件数据目录（不存在时宿主会创建），顺带验证其实际位置
        plugin_data_path = self.get_data_path()
        logger.info(
            f"【合璧字幕】{self.__class__.__name__} v{self.plugin_version} 加载成功，"
            f"启用状态={self._enabled}，数据目录={plugin_data_path}"
        )

    def get_state(self) -> bool:
        """返回插件是否启用，宿主据此决定是否注册服务等。"""
        return self._enabled

    def get_api(self) -> List[Dict[str, Any]]:
        """插件 API 声明：冒烟阶段没有接口。"""
        return []

    def get_form(self) -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Any]]:
        """配置页（Vuetify JSON）：只有一个绑定 enabled 的开关；第二项为默认配置。"""
        form_components = [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "enabled", "label": "启用插件"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
        default_config = {"enabled": False}
        return form_components, default_config

    def get_page(self) -> Optional[List[Dict[str, Any]]]:
        """详情页：冒烟阶段没有。"""
        return None

    def stop_service(self) -> None:
        """停用、重载、卸载时调用：当前没有后台资源需要释放，只记录日志。"""
        logger.info(f"【合璧字幕】{self.__class__.__name__} 服务已停止")
