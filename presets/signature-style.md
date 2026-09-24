# Signature style — how the look gets applied

There is no house look baked into this folder. The look comes from **`brand-kit.md`**, applied once into
`presets/brand.json`, and every builder reads that file. This page explains what each value drives, so you can
predict what changes when you change it.

| `brand.json` key | Set in brand-kit.md | What it drives |
|---|---|---|
| `hero` | section 3 | the strip behind the on-screen ask, the top bar of the brand check, the accent in the sweep intro example |
| `accent` | section 3 | the emphasis words in the ask line; ember/glow tint in the layout example |
| `dark` | section 3 | reading-card backgrounds, panel backgrounds |
| `text` | section 3 | caption and card text color |
| `font_headline` | section 4 | the ask line, titles, stat callouts, thumbnail strip |
| `font_caption` | section 4 | captions, reading cards |
| `caption_px` | section 4 | caption size at 1080 wide (scales with the frame) |
| `intro` / `outro` / `outro_music` / `bed` | section 5 | which clips the intro, outro and music steps use — or `none` to skip the step |
| `ask_line` / `logo` / `ask_at` | section 6 | the on-screen subscribe strip: text, logo file, when it appears |
| `thumbnail_look` | section 7 | the paragraph the thumbnail prompt is built around |
| `corrections` | section 8 | merged into `presets/caption-corrections.json` |

## The three rules that don't change with the brand

1. **Safe zones are not style.** 9:16 keeps everything between y 200 and 1620; 16:9 keeps the bottom 10% and
   the bottom-right corner clear. No color choice overrides that.
2. **Captions are white-on-dark or the owner's `text` on black, never on a busy background.** Legibility on a
   phone beats any palette.
3. **One accent, used sparingly.** If everything is the accent color, nothing is.

## Changing the look later

Edit `brand-kit.md`, run `apply my brand kit` again, re-render the brand check, then re-run the builders on the
job you're on. Nothing else needs touching — that's the point of one file.

## The examples in `presets/`

`sweep-intro`, `outro`, and `free-carry-layout` are the original author's look. Their scripts take colors, fonts,
text and clips as inputs (defaults now pulled from `brand.json`), so they'll produce *your* version of the same
mechanism. If the mechanism itself isn't your style — you don't want a sweep, you don't want a strip — leave
`intro: none` and `ask_line` empty and they never run.
