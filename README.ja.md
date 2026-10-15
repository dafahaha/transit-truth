# TransitTruth 🛡️

[English](README.en.md) · [中文](README.md) · [日本語](README.ja.md)

![TransitTruth Banner](docs/banner_1280x640.png)

**APIリレーで `gpt-4o-mini` の料金を支払っているとして、本当にそのモデルが返ってきていますか？**
TransitTruthは、ステートレスなCLIツールです。OpenAI互換のエンドポイントに対して限定的なフィンガープリントプローブ群を実行し、エンドポイントが提供を主張（claim）しているモデルがリファレンスのフィンガープリントと一致しているかどうかを、単一のJSONレポートで提示します。

LLMセキュリティ研究者、エージェント開発者、サードパーティ製のリレーやゲートウェイ経由でLLMトラフィックをルーティングするすべての人のために開発されています。

---

## クイックスタート

```bash
pip install transit-truth
# セルフホストのreference-serverで本物のローカルTokenizerを使用する場合（このエクストラが
# ない場合、後述のAPIキー不要パスは配管確認用のスタブへと安全に縮退します）:
pip install "transit-truth[reference]"
```

対象のリレーと、それが提供を主張しているモデル名を指定して実行します。APIキーは環境変数から読み取られ、ディスク、ログ、レポートには一切保存・出力されません。

```bash
export TRANSIT_TRUTH_API_KEY=sk-your-key
transit-truth verify --base-url https://your-relay.com/v1 --model gpt-4o-mini
```

標準出力（stdout）に機械可読な単一のJSONレポートが出力されます:

```json
{
  "claimed_model": "gpt-4o-mini",
  "verdict": "pass",
  "confidence": "medium",
  "statistics": {
    "matched_reference_model": "gpt-4o-mini",
    "posterior": 0.87,
    "tokenizer_consistency": {"score": 1.0, "verdict": "match"}
  },
  "disclaimer": "Probabilistic auxiliary evidence, NOT a cryptographic proof."
}
```

終了コード（Exit code）: `pass` **または** `insufficient_evidence` の場合は `0`、`suspicious` の場合は `3`、実行エラーの場合は `2` です。スクリプト等で自動判定する場合は、終了コードではなくJSONの `verdict` フィールドを参照してください。

### 有料キーがない場合: パイプライン全体をローカルで実行

セルフホスト可能なOpenAI互換リファレンスバックエンドが同梱されています。verifyクライアントは空ではないAPIキーを必須とするため、ダミー値を設定してください:

```bash
export TRANSIT_TRUTH_API_KEY=local-dummy-no-billing   # 請求は発生しません（ローカル専用）

# ターミナル 1: ローカルリファレンスバックエンド（本物のQwen Tokenizerによるトークン数カウント、
# 決定論的スタブコンテンツ。実モデルやGPUは不要）
transit-truth reference-server --model qwen2.5-0.5b-instruct --port 8765

# ターミナル 2: 自分自身に対して検証を実行
transit-truth verify --base-url http://127.0.0.1:8765/v1 \
    --model qwen2.5-0.5b-instruct --allow-local
```

ループバックアドレス（localhost）を対象とする場合は `--allow-local` が必要です。デフォルトではパブリックURL向けのSSRF保護が有効になっています。本物のTokenizerがダウンロードできない場合（`HF_ENDPOINT` のデフォルトは `https://hf-mirror.com`）、reference-serverは明示的にラベル付けされた配管確認用スタブ（plumbing stub）へと縮退します。標準エラー出力（stderr）のバナーおよび `GET /v1/models` の `mode` フィールドにその旨が明記され、いかなる検証・保証も行えません。

## 3つの判定（Verdicts）

| verdict | 意味 |
|---|---|
| `pass` | 観測されたフィンガープリントが、リファレンスと統計的に一致している。 |
| `suspicious` | 観測されたフィンガープリントが大きく異なる（例: 異なるモデルファミリー）。 |
| `insufficient_evidence` | リファレンスが存在しない、サンプル数が少なすぎる、またはエンドポイントが応答を拒否した — 推測による判定は**行いません**。 |

`suspicious`（疑わしい）という判定は、「不正が証明された」ことを意味するわけではありません。さらなる詳細な調査が必要であることを示す証拠です。

## 実際の動作の仕組み

主張されたモデル名に対して、デフォルトのプローブ群は計17回のリクエストを送信します。内訳は、5回のTokenizerプローブ（固定プロンプト群に対する自己報告の `usage.prompt_tokens`）と、4種類の振る舞い（Behavioral）プローブ×3回試行（モデルが返す数字、コイントス、動物、文字などの分布的な「ランダムタスク」の偏り）です。観測されたフィンガープリントを同梱のリファレンスカタログとカイ二乗（chi-square）検定、コルモゴロフ–スミルノフ（KS）検定、およびベイズ事後確率を用いて比較し、単一のレポートを出力します。全体の実行コストは0.01ドル未満です。

## 明確な限界事項（Honest limitations）

いかなる判定結果を信頼する前にも、必ず以下をお読みください。

- **暗号学的な証明ではなく、確率論的な補助証拠であること。** ブラックボックスのフィンガープリントは偽装可能です。プロバイダーによる署名付きレスポンス（公式アテステーション）のみが最終的な解決策です。本ツールは安価で再現性のあるスクリーニング層であり、法廷で通用する決定的な証拠ではありません。
- **カバレッジは設計上限定的であること。** 現在同梱されているリファレンス:
  - `gpt-4o-mini` および `gpt-4o` — **公式のOpenAIエンドポイントではなく、単一のサードパーティ製リレー（wolfai.top）** を通じて収集された n=50 のベースライン。当プロジェクトが主張するのは、当該リレーにおいてこれら2つのエンドポイントが識別可能であったという事実のみであり、ベンダー非依存のフィンガープリントではありません。
  - Qwen2.5-0.5B-Instruct — 本物のローカルTokenizerカウントのみで、**振る舞いの分布データはありません**。そのため、単体で `pass` 判定となることはありません。
  - DeepSeek-R1-Distill-Qwen — Qwen2のTokenizerから派生しているため、カウントのみでQwenと区別することはできません。GLMはカタログ化されていますがTokenizerのダウンロード待ちです。
  - Claude / Gemini / その他のGPT系モデルのフィンガープリント収集には、ご自身のAPIキーが必要です。
- **Temperature=0 における一点集中（point-mass）リプレイのリスク。** 同梱されている振る舞いベースラインは退化した分布です（例: gpt-4o-mini は「1〜10の中から数字を1つ選んで」というプロンプトに対して毎回必ず "7" を返します）。プローブのプロンプトとベースラインはこの公開リポジトリに含まれているため、攻撃者は約4つの公開最頻文字列をハードコードすることで、振る舞いの一致（match）を決定論的に再現できてしまいます。レポートではまさにこの理由から `deterministic_replay_risk` フラグを立て、信頼度（confidence）の上限を `low` に制限します。
- **Tokenizerカウントは自己報告による弱いシグナルであること。** リレーは自身が報告する数値をコントロールできます。また、異なるモデルファミリーであっても公開プローブ上でほぼ同一の結果になることがあります（Qwen2.5 と o200k は5つのプローブのうち4つで一致します）。主要な判断基準となるのは振る舞いの証拠であり、Tokenizerの一致のみからモデルファミリーを推測してはなりません。
- **ε希釈（ε-dilution）。** トラフィックのごく一部のみを偽のモデルにルーティングするリレーを、少数のリクエスト予算内で検出することは困難です。`app.verify.sequential.budgeted_sequential_analysis(epsilon, budget)` を使用することで、指定した予算内でどの程度の割合を検出できるかを推計できます。

完全なレポート仕様については [docs/verify.md](docs/verify.md) を、方法論や脅威モデルについては [docs/tech_report.pdf](docs/tech_report.pdf) を参照してください。

## Python SDK とオブザーバビリティ

```python
from app.verify import verify_endpoint_sync

report = verify_endpoint_sync(
    base_url="https://relay.example/v1", claimed_model="gpt-4o-mini"
)
```

オプションとして、[`examples/`](examples/) 配下に OpenTelemetry / OpenInference エクスポーター、DeepEval メトリクス、および Langfuse スコアの統合例を用意しています。

## CLI以外のリポジトリ構成

本リポジトリには、CLIの母体となったより広範な監査プラットフォームも同梱されています。リレー監査用のFastAPI Web UI、コミュニティリーダーボード、収集されたベースラインデータセット、および詳細な技術レポートが含まれます。

- **オンラインデモ（インストール不要）:** https://dafahaha.github.io/transit-truth/
  — すべてブラウザ上で動作し、APIキーがサーバーに送信されることはありません。
- **Webプラットフォームの実行:** `cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000`
- **Docker:** `docker-compose up -d`（UIDやプロキシに関する注意点はREADMEを参照してください）。
- **ベースラインデータ:** `data/baselines/`（実際の n=50 の収集データ）、`data/fingerprints/`（オープンソースモデルのTokenizerカタログ）。
- **テスト:** 249 passed / 7 skipped（スキップされた7件は実際のAPIキーが必要な統合テストです。`pytest -m integration` で実行できます）。

## ソースコードからのインストール（PyPIリリース前）

```bash
git clone https://github.com/dafahaha/transit-truth.git
cd transit-truth
pip install .
# reference-serverで本物のローカルTokenizerを使用する場合:
pip install ".[reference]"
```

`data/baselines/` または `data/fingerprints/` を変更した場合は、wheelをビルドする前に `python sync_reference_data.py` を実行してください。インストールされるパッケージには、これらカタログのミラーが含まれます。

## コントリビューション（貢献について）

IssueやPRを歓迎します。初心者向けの課題には [`good first issue`](https://github.com/dafahaha/transit-truth/labels/good%20first%20issue) タグが付いています（新しいオープンソースモデルのTokenizerフィンガープリントの追加、OTelエクスポーターのサンプル、ドキュメントの翻訳など）。[CONTRIBUTING.md](CONTRIBUTING.md) および [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) を参照してください。

リレーを監査した場合は、その結果を [Discussions → Show your audit results](https://github.com/dafahaha/transit-truth/discussions) に投稿してください。

## 引用（Citation）

```bibtex
@misc{transittruth2026,
  title  = {TransitTruth: Stateless Verification of Model Identity for OpenAI-Compatible Endpoints},
  author = {dafahaha},
  year   = {2026},
  howpublished = {\url{https://github.com/dafahaha/transit-truth}},
}
```

## 免責事項（Disclaimer）

本ツールは研究目的のツールです。結果は統計的証拠であり、法的証拠ではありません。対象サービスの利用規約を遵守し、エンドポイントに過度な負荷をかけないでください。本プロジェクトは、OpenAI、Qwen、あるいはいかなるモデルプロバイダーとも提携していません。

## ライセンス

MIT — [LICENSE](LICENSE) を参照してください。
