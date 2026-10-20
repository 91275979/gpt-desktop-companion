# GPT 桌宠 1.0

Windows 上使用 Python 与 PySide6 制作的 GPT 风格桌面角色，支持透明置顶、角色状态动画、互动情绪、Codex 配额、天气和主要市场行情。

## 下载与首次安装

1. 打开 GitHub 的 **Releases** 页面，在最新版本下下载 **Source code (zip)**。
2. 解压到普通文件夹，不要直接在压缩包内运行。
3. 安装 [Python 3.11 或更高版本](https://www.python.org/downloads/windows/)，安装时勾选 **Add Python to PATH**。
4. 双击 `install.bat`，等待它创建项目专用 `.venv` 并安装 PySide6。
5. 安装完成后双击 `start.vbs` 启动；以后只需要双击 `start.vbs`。

源码用户也可以点击 GitHub 仓库右上角 **Code → Download ZIP**。本项目使用 [MIT License](LICENSE) 开源。

## Windows 启动和快捷方式

- 双击项目根目录的 `start.vbs`：无终端窗口启动，推荐日常使用。
- 双击 `start.bat`：转交给同一隐藏启动入口，cmd 窗口会立即退出，可能短暂闪现。
- 优先使用 `.venv\Scripts\python.exe`；没有虚拟环境时尝试系统的 `py -3`。缺少 PySide6 时弹出包含安装命令的提示，不会无提示退出。

创建桌面快捷方式：在 Windows 桌面右键 → 新建 → 快捷方式，位置填写：

```text
C:\Windows\System32\wscript.exe "D:\gpt-desktop-companion\start.vbs"
```

命名为“GPT 桌宠”。以后双击此快捷方式即可打开。也可以右键 `start.vbs` → 显示更多选项 → 发送到 → 桌面快捷方式。不设置开机启动。

默认尺寸为中（180 个 Qt 逻辑像素），卡片右上角“⋯”设置中可选择小 150 / 中 180 / 大 220。Windows 显示缩放仍由 Qt 处理。`config.json` 在首次选择或退出时自动生成，保存尺寸、置顶、面板显示状态及窗口位置；下次启动恢复。位置超出当前屏幕工作区时回到右下角，距任务栏和边缘 24 个逻辑像素。配置损坏时使用默认值。

新增 `settings.py` 管理偏好，`launch.py` 处理依赖及启动失败提示，`start.vbs` 提供隐藏启动。配置文件不提交到 Git。删除 `config.json` 可以恢复默认设置（先退出桌宠）。

日常启动无需 API Key，不自动调用模型；默认通过本机 Codex 的只读接口获取配额。另有可选的 Responses API usage 接入模块。

## 启动

本机准备好 `.venv` 后，双击 `start.bat` 即可运行。
也可以在项目目录的 PowerShell 中执行（能看到报错）：

```powershell
.\.venv\Scripts\python.exe main.py
```

桌宠出现在主屏幕右下角、任务栏上方。点击进入 happy 并显示“主人好！”，约 1 秒后恢复 idle，气泡独立计时 1.5 秒后隐藏；重复点击重新计时。拖动不触发 happy 或问候。右键打开卡片，在右上角“⋯”菜单选择“退出程序”可关闭。更新素材后需重启。

## 三页信息卡片

右键角色：卡片隐藏时打开 Usage，已显示时循环 Usage → Weather → Markets → Usage。左右箭头共用同一页面状态；顶部圆点标示页面，× 隐藏卡片，“⋯”保留尺寸、置顶、会话暂停和退出入口。不会触发左键问候。

三页使用同一深色容器（252×550 逻辑像素，矮屏幕自动缩短并可滚动）。默认在角色左侧，靠左边时换到右侧；拖动跟随、切页不移动。打开 180ms 淡入，切页两段各 90ms 轻微淡出/淡入。

- Usage：真实 Codex 额度、重置时间、近一分钟变化。不展示无真实来源的 Token 0、费用和速度；已有真实 API usage 时才启用该区域。
- Weather：真实 Open-Meteo 当前天气及当天预报，按温度/体感、雨和风生成规则型穿衣建议；不调用模型，也不读取 Windows 天气小组件。未配置城市时提供“设置所在城市”按钮；点击输入 Tokyo、Tokyo, Japan、Xi'an, China 等，保存后立即刷新。
- Markets：Yahoo Finance 六个指数的当前/最近收盘值及相对前一交易日收盘的变化，标记行情时间、交易状态和可能延迟；不提供投资建议。

配置在 `config.json`，例如（城市仅为示例，请填写自己的城市）：

```json
{
  "dashboard_page": "usage",
  "weather_location": "Breda, Netherlands",
  "market_refresh_minutes": 2,
  "market_color_scheme": "cn",
  "weather_refresh_minutes": 20,
  "watchlist": []
}
```

这些字段与现有尺寸、位置等字段共存，保存窗口偏好不会删除它们。天气刷新限制 15～30 分钟，市场刷新限制 1～5 分钟；启动各请求一次，不在翻页时重复请求。watchlist 仅保留配置，尚不请求自选股。城市可直接在 Weather 页设置/更改，无需编辑 JSON，保存成功后立即生效；手动修改刷新周期后重启生效。最后停留页面会保存；恢复可见卡片时恢复该页，隐藏后右键重新打开仍按交互要求回到 Usage。

HTTP 请求在有超时和体积限制的后台线程进行，默认校验 HTTPS 证书，Qt 主线程只处理结果。网络失败不清空本次运行中上次成功数据；关闭后不再交付请求结果。Yahoo 公开图表接口可能限流或变更，届时显示失败及旧数据，provider 可独立替换。

数据来源：[Open-Meteo 文档](https://open-meteo.com/en/docs)、[地理编码](https://open-meteo.com/en/docs/geocoding-api)、[Yahoo Finance S&P 500](https://finance.yahoo.com/quote/%5EGSPC/)。天气为模型数据，并非本地实测温度。

实际数据页面检查（不会保存示例城市）：

```powershell
.\.venv\Scripts\python.exe check_dashboard.py --weather-location "Breda, Netherlands"
.\.venv\Scripts\python.exe check_dashboard.py --page markets
```

新增 `usage_page.py`、`weather_page.py`、`markets_page.py`，容器继续使用 `panel.py`；`dashboard_services.py` 装配数据源；`weather_provider.py`、`market_provider.py` 与通用 `http_client.py` 负责异步数据获取。

## Codex 配额接入

已接入用户提供的 CodexQuotaWidget 所使用的同一数据协议，直接使用本机 Codex，无需额外运行 ZIP 中的 .NET 悬浮窗，也无需 API Key。

- 自动定位 `codex.exe`，通过 stdio 完成 initialize / initialized 握手，再调用 `account/rateLimits/read`。
- 正式启动读取一次，此后每 2 秒刷新；异步 QProcess 不阻塞动画，上次请求未完成时跳过以避免堆积。15 秒超时后退出本程序创建的子进程，下轮重试。
- 右键打开 Usage 页查看 5 小时和每周剩余百分比、当地时间的重置时间。优先使用 `rateLimitsByLimitId.codex`，按 300 / 10080 分钟辨认窗口。
- 缺失的窗口显示“不可用”；读取失败时标记错误并保留上次结果。不会把别的周期或产品的数据作为替代。
- 配额与 API token 账本分开。首次读取只建立基准；没有变化不弹窗。已用额度增加时浮窗显示各周期“-x%”与“剩余 y%”（变化单位为百分点），同时变化在同一浮窗分行显示，绝不跨周期相加。额度浮窗淡入 180ms、停留 1620ms、淡出 700ms，总计 2.5 秒。新变化合并到现有浮窗并延长停留；淡出期间平滑恢复，不叠加窗口。重置、额度下降或容量改变时重新建立基准。
- `quota_provider.py` 输出统一 `QuotaUpdate` / `QuotaSnapshot`，包含 total、used、remaining、percentage（已用百分比）、reset_time、fetched_at，以及 source / period / unit。此来源的 total=100 仅表示百分比刻度，不代表 token 总额。未来只有明确提供 token 单位的来源才显示“- xxx tokens”。
- `UsageTracker` 保存最近成功快照及本次运行最近 1 分钟的额度增量；面板显示剩余、已用、使用率、最近 1 分钟变化、重置时间。失败显示“额度数据暂不可用”并标记旧数据；恢复后比较上次成功值，变化可能覆盖整个断线期间。额度快照只存内存，API usage 账本仍保留原有持久化。
- 登录与网络请求由本机 Codex 处理；桌宠不读取 auth.json、Cookie、令牌，不创建任务、不发送模型请求、不消耗重置次数。关闭桌宠时只关闭它自己创建的 app-server 子进程。

如 Codex 不在 PATH，可在环境变量 `CODEX_EXECUTABLE` 指定其完整 exe 路径。需先在 Codex 中登录 ChatGPT 账户。正式启动可加 `--no-quota` 禁用连接，usage 演示模式默认不连配额接口。

单次真实只读检查：

```powershell
.\.venv\Scripts\python.exe check_codex_quota.py
```

协议依据 [OpenAI 官方 App Server 文档](https://learn.chatgpt.com/docs/app-server)。这是对该工具读取方式的 Python 接入，不是将其 EXE 嵌入桌宠。

## Token 增量展示

`UsageTracker` 实时接收 API 返回的 usage；UI 的 QTimer 每 **2000 ms** 消费新增 delta。没有新增 token 时不弹提示，也不发送网络请求。面板读取快照不会消耗 popup 的 delta。

头顶深灰透明提示显示 token 总量、Input / Output 和估算费用，鼠标可穿透，不影响拖动：

- 0～200 ms：淡入并上移 6 px。
- 200～1800 ms：保持可读。
- 1800～2400 ms：淡出并继续上移 4 px。
- 未消失时收到新增量：累加到当前数字；保持阶段延长，淡出阶段平滑恢复不闪烁。不会堆叠多个窗口。

正常启动没有模拟消耗；未收到真实 usage 时隐藏 Token 详情。统计仅覆盖**本桌宠接入点记录的请求**，不是 ChatGPT/Codex 账户总用量，也不会读取其他软件的请求。

演示（无网络、使用内存账本、明确显示“模拟”）：

```powershell
.\.venv\Scripts\python.exe main.py --demo-usage
# 自动演示 13 秒后退出：
.\.venv\Scripts\python.exe main.py --demo-usage --demo-seconds 13
```

演示在约第 2 秒显示 1,284 tokens，第 4 秒累加到 1,484；中间无新 usage 的轮次不会新弹窗，第 10 秒显示下一笔。模拟费用只是动画样例。

## 数据与真实 API 接入

`usage_tracker.py` 保存 input_tokens、output_tokens、total_tokens、cached_tokens、reasoning_tokens、estimated_cost、session_total、today_total、last_update。`snapshot()` 的 Input/Output/费用是本次会话累计；`consume_delta()` 只返回上轮结算后的增量。可选字段未知时为 None，不当作 0；混合已估价与未估价记录时费用显示“费用未配置”，避免漏算后显示为完整费用。

正式账本在 `data/usage.sqlite3`，记录 usage 原始字段（包括未来扩展字段）、response ID 和时间；不保存提示词、回复正文或密钥。response ID 去重，每次重启会话归零，今日累计按系统本地日期保留并在跨天时重算。最近使用速度是最近五分钟已记录 token × 12，不是实时生成速度。新增数据库和 `.env*` 已被 Git 忽略。

可选 SDK 已在本机安装；新电脑如需调用 API，再安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
```

将真实密钥配置在 Windows 环境变量 `OPENAI_API_KEY` 后重新打开终端/启动桌宠。项目不读取 `.env`，不把密钥写入源码、日志或 UI。SDK 从环境变量读取密钥，见 [OpenAI 官方 Quickstart](https://developers.openai.com/api/docs/quickstart)。

已有 API 请求结束后，可在同一进程直接接入当前桌宠的 tracker：

```python
pet.tracker.record_response(response)  # 仅读取 response.usage，不估算字符串长度
# 已明确计算每次请求费用时：
pet.tracker.record_response(response, estimated_cost="0.001234")
```

或者使用准备好的异步包装器（在工作线程的 asyncio 事件循环中调用，勿在 GUI 线程 asyncio.run）：

```python
from openai_usage import TrackedResponsesClient

async def request(tracker, model, prompt):
    api = TrackedResponsesClient(tracker)
    try:
        return await api.create(model=model, input=prompt)
    finally:
        await api.close()
```

模型由调用方明确指定，没有硬编码默认模型或价格。可传 `cost_estimator(response)` 提供按实际模型、缓存和服务层级计算的估价；未配置时显示“费用未配置”，不是 $0。估价不等于账户余额或官方账单。当前包装器支持非流式、非后台请求；流式接入应在最终 response 到达时记录一次完整 usage，不记录每个文本块。缺失 usage 时不猜测，请求失败不凭空记账。

字段依据 [OpenAI 官方 usage 示例](https://developers.openai.com/api/docs/guides/reasoning)：cached_tokens 已包含在 input_tokens 中，reasoning_tokens 已包含在 output_tokens 中，不重复相加。本阶段已用 SDK 数据对象和模拟客户端验证接入，**没有执行真实付费请求**。

## 角色素材

素材目录：`assets/characters/`。每个状态可使用一张 `<状态名>.png`，也可使用 `animations/<状态名>/000.png`、`001.png` 等逐帧透明 PNG。同名逐帧动画优先于静态图；`gpt_assistant.png` 仅在 `idle.png` 缺失时作为旧版备用。

`character.py` 在加载阶段按 alpha≥24 测量可见区域，忽略透明边距和极淡噪声，以 idle 的可见高度为基准等比对齐各状态，放入同一个透明画布，统一水平中心和脚底位置。逐帧动画使用整段共用的可见区域，保留帧间动作位移，避免每帧重新裁剪导致跳动。

上述归一化只执行一次，不修改磁盘原图。显示时各状态共用一个约 180 px 高的显示框、一套缩放和同一个底部中心锚点，不按当前图片边界重新缩放。不同尺寸和透明留白的素材也会归一化；素材内部姿势或头身比例差异无法仅靠整体对齐消除，制作表情图时仍应尽量只修改脸部。

角色默认高 **180 个 Qt 逻辑像素**，宽度按比例计算；Windows 150% 显示缩放下对应约 270 个物理像素。窗口距屏幕工作区右边和下边各 24 个逻辑像素，并为动画与气泡预留透明边距。逐帧图启动时缓存至最高 768 像素高，按当前帧的 alpha 检测点击；透明区和 alpha 小于 24 的极淡边缘不会触发点击或拖动。

## 多状态动画

现已提供十种状态各 12 帧的透明 PNG 动画和独立 `preview.webp`，总览见 `assets/characters/animations/contact_sheet.png`。完整帧序列位于 `assets/characters/animations/<状态名>/`，文件名用补零编号保证播放顺序。所有帧须为同尺寸真实透明 PNG，身体和脚底位置应在同一画布上保持稳定。`animations/manifest.json` 可设置 `default_fps` 和 `fps` 中的单状态帧率；本套素材按状态设置 4～75 FPS，其中眨眼 75 FPS 对应约 160 毫秒。状态切换时动画从首帧播放并循环，损坏的序列回退到同名静态图。支持 `idle`、`blink`、`happy`、`talk`、`thinking`、`embarrassed`、`shy_angry`、`angry`、`strong_angry`、`sleep`。前九个状态由现有交互驱动，`sleep` 由调用方主动切换。源图及重新生成方法见 `assets/characters/README.md`。

- idle 时随机等待 3～6 秒，进入 blink 160 毫秒后恢复 idle，重新安排下一次眨眼。
- happy 持续 1 秒后恢复 idle；talk/thinking 持续到主动切换，不被自动眨眼打断。显式切换覆盖旧的恢复计时。
- 保留 5.6 秒周期内 100%～100.4% 的微呼吸，悬停平滑放大至 102.5%，移开恢复。锚点固定在脚底中心，表情切换不重置悬停或呼吸。
- 按住鼠标时冻结状态计时、悬停缩放和呼吸；拖动结束不触发 happy。隐藏窗口时停止动画计时器。气泡使用独立的一次性计时器，不因拖动或眨眼延迟消失。
- 所有图片启动时缓存，切换状态和动画帧不重复读文件，使用单个约 30 FPS 定时器。

```python
pet.set_character_state("talk")
pet.set_character_state("thinking")
pet.set_character_state("idle")
pet.set_character_state("sleep")
# 控制器接口也可直接调用，支持 CharacterState 枚举：
pet.animation.set_state("happy")
print(pet.animation.state)            # 逻辑状态
print(pet.animation.displayed_state)  # 缺图时实际显示 idle
print(pet.assets.unavailable)         # 不可用素材及原因
print(pet.assets.invalid_animations)  # 无效动画及原因
pet.animation.state_changed.connect(print)
```

状态、素材和绘制集中在 `character.py`，未来可保持窗口接口并替换渲染后端；本版本未集成 Live2D。无效状态名抛出 ValueError，原状态不变。

缺失、损坏、全透明、不透明或没有足够可见像素的可选状态图回退 idle。不同画布尺寸会自动归一化。idle 缺失时尝试旧版 gpt_assistant.png；二者均不可用时显示明确提示并退出。素材中的背景和文字仍需提前清理。

## 在新电脑安装

先安装 Windows 版 Python 3.11 或更新版本（推荐 3.12/3.13），然后在项目目录执行：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

虚拟环境无需激活。当前机器的虚拟环境基于 Codex 自带 Python 创建；移动项目或移除该 Python 后，需重新创建 `.venv`。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试覆盖窗口、透明像素、尺寸、拖动、眨眼随机间隔、happy 恢复与重复计时、状态优先级、缺图回退、画布对齐、缓存和微呼吸。测试用几何图仅写入临时目录，不作为项目角色素材。

## 文件

- `main.py`：桌宠绘制、窗口属性、拖动、点击和退出。
- `usage_tracker.py`：线程安全 usage 账本、去重、增量结算与累计快照。
- `codex_quota.py`：本机 Codex 协议连接、配额解析与刷新。
- `quota_provider.py`：真实来源适配和统一快照接口，负责每 2 秒异步读取。
- `tests/test_quota_provider.py`：基准、增量、周期重置、失败恢复和额度浮窗集成测试；测试夹具不用于正式界面。
- `check_codex_quota.py`：默认单次真实配额检查；`--samples 3 --gui` 连续检查并打开真实详情面板，完成后自动关闭，将面板截图保存到忽略提交的 `data/`。
- `tests/test_codex_quota.py`：协议顺序、窗口识别、异常与空值测试。
- `usage_popup.py`：浮动提示、动画、合并和跟随定位。
- `openai_usage.py`：可选的异步 Responses API 包装器。
- `requirements-api.txt`：可选官方 OpenAI SDK 依赖。
- `panel.py`：三页 Dashboard 容器、导航、动画和跟随定位。
- `context_menu.py`：右键菜单、尺寸选项及置顶开关。
- `character.py`：素材加载、透明边距裁剪、动画状态、缓存绘制和动态点击检测。
- `assets/characters/idle.png`：默认透明角色立绘；`gpt_assistant.png` 为旧版备份。
- `assets/characters/README.md`：素材规范。
- `requirements.txt`：PySide6 依赖。
- `start.bat`：双击启动，无控制台窗口。
- `tests/test_pet.py`：Qt 窗口与交互回归测试。
- `tests/test_usage.py`：账本、去重、并发、跨天、API 包装器和浮动动画测试。
- `.gitignore`：忽略虚拟环境、缓存和日志。
- `.venv/`：本机 Python 虚拟环境及已安装依赖，不应提交到版本库。

透明窗口采用 Qt 官方的 `WA_TranslucentBackground` 与 `FramelessWindowHint` 组合，参考 [QWidget 文档](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html)。

## 额度 UI 验证

运行 `.\.venv\Scripts\python.exe demo_quota_popup.py` 可独立模拟 5 小时和每周额度变化、再次变化及拖动跟随；约 5.5 秒自动关闭。它不连接 provider，不改真实账本，界面标注“演示”。截图保存到 `data/quota-popup-demo.png` 和 `data/quota-panel-demo.png`。

正式详情面板采用两张灰阶额度卡片；最近变化表示近 1 分钟观测到的消耗。未记录真实 API token 时隐藏 Token 区域。

## ChatGPT 联动监控

双击 `start_watcher.vbs` 在后台启动监控（无终端、不设置开机启动）。重复启动只保留一个监控实例。双击 `stop_watcher.vbs` 停止监控并保留当前桌宠，之后可以手动退出桌宠。

本机实际检测到的进程名是 `ChatGPT.exe`，Windows“ChatGPT”快捷方式指向 `OpenAI.Codex_2p2nqsd0c76g0!App`。当前监控同时核对可执行文件位于 `WindowsApps/OpenAI.Codex_<版本>__2p2nqsd0c76g0/app/ChatGPT.exe`，防止把其他同名文件当成目标。它对应当前安装包，不代表另一套独立安装的 ChatGPT 客户端。未来切换客户端，应重新核验安装身份并修改 watcher.py 的适配条件。

`watcher.py` 用 Windows 原生进程快照每 2 秒检测一次，仅对同名候选进程读取路径，不轮询 PowerShell、不访问 API。所有匹配进程退出才视为应用完全退出；只关窗口但仍驻留后台时不会关闭桌宠。检测失败不会被误判为应用退出。

目标运行时启动桌宠；发现桌宠被手动关闭后等待 3 秒再拉起（另加最多约 2 秒检测延迟及程序加载时间）。卡片右上角“⋯” → “本次会话不再自动启动”可退出并暂停拉起，直到监控观察到目标完全退出、下一次重新运行。监控期间手动启动的桌宠同样受联动管理。

`instance.py` 使用 Windows 会话内命名 mutex 分别约束 watcher 和桌宠；所有标准启动入口最终都经过同一桌宠锁。命名 event 发起正常退出，由桌宠 Qt 主线程保存 config.json 并关闭自己的配额子进程。监控不使用 taskkill，不强杀目标应用；如果桌宠主线程无响应，会继续发送正常退出请求，单实例锁阻止产生第二只。

验证：单元测试覆盖监控状态、暂停、错误检测及内核锁；受控测试进程验证了启动、退出、手动重开及重复实例。没有为了验证而关闭承载当前开发任务的 ChatGPT/Codex 应用，因此真实目标“完全退出再启动”仍需在任务结束后验证。

## 城市设置与行情配色

天气默认使用当前公网 IP 自动定位（`weather_location_mode: "ip"`）。启动时和每次天气刷新时通过 [ipwho.is](https://ipwhois.io/documentation) 获取城市及经纬度，再向 Open-Meteo 查询天气；默认刷新间隔 20 分钟。定位对应本机请求的网络出口，VPN/代理可能使城市变为出口所在地，不是 Windows GPS 或本地局域网 IP。界面不保存和展示完整公网 IP。

Weather 页“刷新 IP”可立即重新定位；手动设置城市会保存为 `weather_location_mode: "manual"`，以后可点击“按 IP 定位”恢复自动模式。定位或天气失败会标记错误并保留本次运行的上一份成功天气，不把旧城市当成新的 IP 定位结果。

角色首次收到真实天气后会自动弹出穿衣提醒，左键普通互动也会按体感、降雨和风速选择具体建议。自动提醒显示约 4.5 秒，相同建议间隔至少 4 小时，变化后的提醒至少间隔 30 分钟；睡眠、拖动、连续点击情绪状态或已有对话期间延后显示，只保留最新提醒，不累积队列。天气提醒不重置用户互动或睡眠计时。

可运行 `.\.venv\Scripts\python.exe check_weather_ip.py` 验证真实 IP 定位、天气和自动角色提醒；该检查不修改用户配置。

Weather 页的“设置所在城市 / 更改城市”输入框保存到现有 config.json；保存失败会提示且不替换当前 provider。切换城市会清空旧城市展示并丢弃仍在途的旧请求。天气图标为低饱和文本图标，穿衣建议仍由规则生成。

Markets 使用 US / CN 分组的紧凑卡片。统一 `get_market_color(change_percent, scheme="cn")` 默认采用红涨绿跌（#E25555 / #3FAE74），持平灰色；只有涨跌箭头和百分比着色。`market_color_scheme: "global"` 切换为绿涨红跌，重启生效。接近零、四舍五入显示为 0.00% 时采用灰色，避免红绿 -0.00%。
