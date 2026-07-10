pdf/ のdirectoryには七個のsub directoryあります。
各sub directoryには英語版のpdfがあります。
同じsub directoryにはそちらの日本語版のpdfを作成してください。
名前はjapanesepod_{0001}.pdf japanesepod_{0002}.pdfのconventionでお願いします。


japanesepod_0001.pdfは確認しました。完璧です。
残りも宜しくお願いします。

japanesepodの作成ありがとうございます。
次は
同じsub directoryにはjapanesepodの作成と同じで、中国語版のpdfを作成してください。
名前はchinesepod_{0001}.pdf chinesepod_{0002}.pdfのconventionでお願いします。

1:30pm になったので、続いてください。

## reply
ファイル名は指定どおり chinesepod_0001.pdf … chinesepod_0365.pdf です。

中身

日本語版と同じ体裁（英中対訳、A4）で、見出しだけ中国語化しました。
- 对话 / Dialogue：英語原文の各行の下に簡体字中国語訳を併記
- 重点词汇 / Key Vocabulary と 补充词汇 / Supplementary Vocabulary：英単語＋品詞（中国語）＋語義（中国語）の表
- フォントは Noto Sans SC（OFLライセンス・埋め込み）

進め方

日本語版で作った抽出JSONとレンダラを言語対応に一般化し（render_lesson.py ja|zh、check_translations.py zh）、サブエージェントで簡体字に翻訳しました。特殊回（0066のPig Latin暗号会話、0337の詩、0168の語彙のみ）も正しく処理済みです。

途中でセッション上限に当たり後半バッチが失敗しましたが、制限解除後に未完了の107件を再投入して補完しました。最終チェックは missing: 0 broken: 0、全365件が英語版と正しく対応しています。

コミットはしていません。日本語版・中国語版あわせて730件のPDFと scripts/ は未追跡状態です。コミットしてよければお知らせください。

## claude
english_pod/pdf には chinese_version, english_version, japanese_versionのディレクトリがあります。
