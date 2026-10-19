# 图像生成提示词

模式：内置 imagegen。宣传图用于角色造型参考；之后以生成的 `sources/idle.png` 为各表情的编辑目标。所有输出要求真实透明 alpha 背景。最终逐帧动作由 `tools/build_character_animations.py` 从状态原图生成。

## 主立绘 `idle`

> Use case: stylized-concept. Create one standalone centered front-facing chibi anime desktop-pet girl from the attached poster, in her idle state. Long wavy silver-white hair, bright blue eyes, black bow with dark metallic flower hairpiece on viewer's right, black gothic dress with ivory lace, tiny hands at lap, calm gentle gaze. Preserve the poster character's visual identity. Isolated character only, fully visible. REAL transparent background/alpha, no text, no poster, no frame, no other objects, no floor, no glow, no shadow. Production PNG sprite.

## 表情编辑共同要求

> Use case: precise-object-edit. Input target is a transparent sprite of a fictional fully clothed anime mascot. Preserve exactly the same blue-eyed silver-haired character, viewer-right black floral bow, black-and-ivory lace dress, seated silhouette, body proportions, art style, scale, centered placement and real transparent alpha background. Change only facial expression and small hand/head gestures. No text, symbols, scenery, other characters, floor, or cast shadow.

在共同要求后添加对应状态句：

| 状态 | 状态句 |
| --- | --- |
| `happy` | Warm delighted smile, softly crescent eyes, slight cheerful lift of hands. |
| `talk` | Friendly engaged expression, mouth gently open as if saying one syllable, one hand slightly raised. |
| `thinking` | Curious slightly tilted head, eyes looking upward, one fingertip near chin, very subtle puzzled eyebrows. |
| `embarrassed` | Bashful expression, rosy cheeks, eyes glancing slightly aside, hands tucked inward. |
| `shy_angry` | Cute flustered protest, visible blush, small frown and lowered brows, hands drawn close to chest. |
| `angry` | Clearly annoyed yet cute: eyebrows lowered, cheeks puffed a little, direct gaze, arms gently folded. Fully clothed. |
| `strong_angry` | Strongest cartoon frustration, deeply furrowed brows and puffed cheeks, blush and clenched little hands, direct gaze. Keep soft cute nonviolent style. Fully clothed. |
| `sleep` | Peacefully sleeping, eyes fully closed, head resting slightly to one side, hands relaxed near lap, still seated with same clothing and hair. No pillow or other props. |
| `blink` | Neutral resting pose identical to input sprite except both eyes naturally closed for a quick blink. Keep mouth calm and all other details identical. |

`talk_closed.png` 使用 `talk.png` 作编辑目标：

> Use case: precise-object-edit. Edit the transparent mascot sprite for a talking animation in a desktop app. Change ONLY the mouth to a relaxed closed smile for an in-between syllable. Keep every other pixel-level visual detail as close as possible: same fully clothed silver-haired blue-eyed character, raised hand, expression, eyes, hair, dress, jewelry, seated pose, centered placement, scale, transparent alpha canvas. Do not change hands, outfit, lighting, background, or anything else. No text.
