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
videos/ExtraStory_BlackXuanyuan_01.mp4
videos/ExtraStory_BlackXuanyuan_02.mp4
videos/ExtraStory_BlackXuanyuan_03.mp4
videos/Sakura_4_CG12_SP_mux.mp4
videos/Season_CG01_Final_mux.mp4
```

`supplements.json`至少包含`{"schema":1,"kind":"bh2017-locrenasci-external-supplements"}`。7张图片必须存在；视频从7.x资源或补充包中读取。

客户端表单和其他游戏资源从使用者提供的1.9、2.4、7.x输入生成。图片与CG的来源说明见[数据与规则来源](../docs/data-sources.md)。
