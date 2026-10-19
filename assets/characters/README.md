# 桌宠状态动画

情绪特效：`thinking` 带浮动问号；`shy_angry` 带脉动红色青筋符号；`angry` 增加一簇闪动怒火；`strong_angry` 使用更大的青筋符号与双侧怒火；`sleep` 的 Zzz 依次上浮并淡出。特效已写入透明动画帧，由生成脚本统一绘制。

本目录已提供依据用户宣传图重绘的银白长发、蓝眼、黑色发饰与黑白裙装角色。`sources/` 保存透明状态原图；`animations/<状态名>/000.png` 至 `011.png` 是程序直接播放的透明帧。十个状态包括 `idle`、`blink`、`happy`、`talk`、`thinking`、`embarrassed`、`shy_angry`、`angry`、`strong_angry`、`sleep`。根目录新补齐的单张状态 PNG 取自对应动画首帧；原有 `idle.png`、`happy.png`、`blink.png` 未覆盖。有同名动画时以动画为准。

所有动画都是 12 帧、701 × 768 像素，使用相同透明画布与底部落点。待机有微呼吸和发梢轻摆，说话状态交替使用张嘴与闭嘴源图，眨眼在约 160 毫秒内完成，愤怒状态有逐档增强的轻颤，睡眠为慢呼吸。每个状态的 `preview.webp` 是独立的循环预览；`animations/contact_sheet.png` 是状态总览。帧率见 `animations/manifest.json`。

程序启动时自动读取这些帧，左键互动和五档愤怒继续由现有状态机切换；无需修改接口。五档愤怒依次使用 `thinking`、`embarrassed`、`shy_angry`、`angry`、`strong_angry`。`sleep` 当前由调用方显式触发：

```python
pet.set_character_state("sleep")
```

替换素材后重新启动程序。若某一段帧缺失、画布不一致或没有真实透明通道，程序会回退同名静态图，并把原因写入 `pet.assets.invalid_animations`。

要从源图重新生成逐帧素材，使用有 Pillow 的 Python 运行：

```powershell
.\.venv\Scripts\python.exe -m pip install Pillow
.\.venv\Scripts\python.exe tools\build_character_animations.py
```

可通过 `--height`、`--frames` 与 `--mouth-box` 调整输出；运行 `--help` 查看参数。生成脚本不会修改 `sources/` 里的原图。源图使用内置 imagegen，以用户宣传图作为角色造型参考，再以生成的 `idle` 为统一角色参考分别制作表情；`talk_closed` 以 `talk` 为编辑目标，仅闭合嘴部。
