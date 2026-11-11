# 外部补充资源格式

使用者通过`supplements`提供外部ZIP或解压目录。补充包中的图片基于官方素材制作，视频来自官方其他版本提取。它们独立于源码提供，许可说明见[NOTICE](../NOTICE.md)。

```text
supplements.json
README.md
images/gacha/dracula.png
images/gacha/ziyuan.png
images/bridge/celebration.png
images/bridge/github.png
images/announcement/teaparty.png
images/announcement/update.png
images/launcher/app-icon.png
images/gallery/m134.png
images/gallery/unavailable.png
videos/ExtraStory_BlackXuanyuan_01.mp4
videos/ExtraStory_BlackXuanyuan_02.mp4
videos/ExtraStory_BlackXuanyuan_03.mp4
videos/Sakura_4_CG12_SP_mux.mp4
videos/Season_CG01_Final_mux.mp4
```

`supplements.json`至少包含`{"schema":1,"kind":"bh2017-locrenasci-external-supplements"}`。9张图片必须存在；视频从7.x资源或补充包中读取。

图鉴补充图片：`gallery/m134.png` 为 M134 武器图标（两档共用），`gallery/unavailable.png` 为两行文字“暂无资源\n占位显示”，用于缺失的琪亚娜·元旦及材料图片。旧的七图补充包需要补入这两张 PNG。

Gallery supplements require the M134 weapon icon (shared by both rarities) and a two-line Chinese missing-resource placeholder. Older seven-image supplement bundles need these two PNG files.

客户端表单和其他游戏资源从使用者提供的1.9、2.4、7.x输入生成。图片与CG的来源说明见[数据与规则来源](../docs/data-sources.md)。
