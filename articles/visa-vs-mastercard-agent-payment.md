---
title: "Visa vs Mastercard――AIエージェント決済の設計思想が"正反対"な理由"
emoji: "💳"
type: "tech"
topics: ["ai", "agent", "payment", "visa", "mastercard"]
published: true
---

## はじめに

AIエージェントが人間の代わりに買い物をする。ChatGPT、Gemini、Copilot、Perplexityが相次いでショッピング機能を実装し、2026年、これはもう仮定の話ではなくなった。

Visaは2026年を「メインストリーム採用の年」と公式に位置づけ、Mastercardは2025年4月に「Mastercard Agent Pay」を発表した。Stripe、Google、PayPalも独自のプロトコルやプロダクトをぶつけている。

ところが中身を覗くと、カードネットワーク2強が正反対の設計思想でこの問題を解こうとしていることが分かる。Visaは「エージェントを認証する」、Mastercardは「ユーザーの意図をトークン化する」。本記事では両社のアーキテクチャを対比し、プロトコル戦争の全体地図までを整理する。

決済プロトコルの基礎知識は前提としない。暗号署名やトークン化は都度説明を添える。

---

## エージェント決済が解こうとしている問題

### 既存のカード決済が前提にしていたもの

クレジットカード決済の仕組みは、長らく「人間がブラウザで、自分の意思で、決済ボタンを押す」という暗黙の前提で動いてきた。不正検知システム(Visa Advanced Authorization、Mastercard Decision Intelligence など)は、この前提に沿って磨かれてきている。

- IPアドレスから普段の地理的パターンを学習する
- マウス操作やキーストロークの行動バイオメトリクスを解析する
- 同一デバイス・同一ブラウザからのアクセス履歴を蓄積する
- カード入力スピードや入力エラーのパターンで人間と機械を区別する

これらの不正検知シグナルは、人間の身体的な動作の癖を前提に設計されている。

### エージェントが入ると何が壊れるか

ここにAIエージェントが入ると、これらの前提が一気に崩壊する。

1. 行動シグナルの消失: エージェントは0.1秒で決済ボタンを押す。人間特有のためらいやスクロール挙動はない
2. IPアドレスの曖昧化: エージェントはクラウド上で動くため、ユーザーの居住地と無関係なIPから決済が発生する
3. クレデンシャルの取り扱い: エージェントにそのままカード番号を渡すわけにはいかない。プロンプトインジェクションでカード情報を抜かれるリスクが現実的に存在する
4. 紛争解決の不能化: 「私はそんな購入をエージェントに指示していない」と言われたとき、ユーザーが本当に指示したのかを証明する手段が必要になる
5. スコープ制限の必要性: 「食料品だけ」「月5万円まで」「3時間以内」といった制約をエージェントに課す仕組みが必要になる

これを抽象化すると、エージェント決済の中核課題は次の3つに集約される。

- Authorization(認可): ユーザーがエージェントに購入権限を与えたことを、どう証明するか
- Authenticity(真正性): エージェントの要求が、ユーザーの真の意図を反映していることを、どう検証するか
- Accountability(責任所在): 何かが起きたときに、ユーザー・エージェント開発者・マーチャント・イシュアーのうち、誰の責任なのかをどう切り分けるか

これは、GoogleがAP2(Agent Payments Protocol)仕様の中で「3A問題」として定式化したものだ。Visa、Mastercard、Stripeを含む業界全体がこのフレームワークで問題を理解している。

この同じ問題に対して、VisaとMastercardが正反対のアプローチを取っている。ここが面白い。

---

## Visaのアプローチ: エージェントを認証する

### Visa Intelligent Commerce(VIC)の全体像

Visaの解は「エージェントそのものを認証・登録する」というアプローチに集約される。2025年4月に発表され、2025年12月までに数百件の実取引を完了させた「Visa Intelligent Commerce」は、次の4つの統合サービスから成る。

1. Agent Onboarding: エージェント自体をVICプラットフォームに登録する
2. Agent-specific Tokens: エージェント専用の決済トークンを発行する
3. User Authentication: Passkeyベースの本人確認を行う
4. Commerce Signals: 購入結果のシグナルをVICに返し、紛争解決に使う

ポイントは、エージェントを「Visa公認のエージェント」として事前登録するモデルを採っていることだ。OpenAIのChatGPTやGoogleのGeminiといったエージェントプロバイダーは、Visaにオンボーディングして登録IDを取得し、Visaが発行する公開鍵基盤(PKI)に組み込まれる。

### Trusted Agent Protocol(TAP)— 署名でエージェントを証明

VICの根幹を支えるのがTrusted Agent Protocol(TAP)で、IETFのRFC 9421(HTTP Message Signatures)を基盤としたHTTPリクエスト署名プロトコルだ。エージェントがマーチャントサイトにアクセスする際、リクエスト全体に暗号署名を付ける。

```http
GET /products/12345 HTTP/1.1
Host: merchant.example.com
Signature-Input: sig1=("@method" "@path" "@authority" "content-type")
                 ;created=1714579200;expires=1714579260;keyid="visa-agent-openai-001"
Signature: sig1=:MEUCIQDc...:
Agent-Consumer-Recognition: <encoded ID Token>
```

この仕組みのキモは以下の通りだ。

- 公開鍵がVisaに紐づいている場合、それは「Visa Intelligent Commerce プログラムへの参加・準拠」を意味する(Visa Developer ドキュメントより)。マーチャントは公開鍵をTrusted Key Storeから取得して署名を検証するだけで、「これは本物のエージェントか」を判断できる
- タイムスタンプとnonceで再生攻撃を防ぐ。リクエストの`created`と`expires`、そして使い捨てのnonceにより、署名の使い回しを防止する
- IPアドレスやヘッダー追加に依存しない。従来のボット検知はIPアドレスやヘッダー操作に依存していたが、TAPはHTTP Message Signatures標準に乗ることでこれを排除している

### Agentic Consumer Recognition Object

エージェントは購入時、そのエージェントが「誰の代理として動いているか」をマーチャントに伝える必要がある。これを担うのがAgentic Consumer Recognition Objectだ。

```json
{
  "id_token": "eyJhbGciOiJSUzI1NiIs...",
  "device_id": "device-fingerprint-hash",
  "country": "JP",
  "postal_code": "151-0061",
  "loyalty_id": "MERCHANT-LOYALTY-12345"
}
```

マーチャントはこの情報から、既存顧客との紐付け、過去の購入履歴の参照、地理的制約のチェック、ロイヤリティプログラムの適用などを行える。

### Agent-specific Token(pass-through token)

決済そのものには「エージェント特化型のpass-through token」が使われる。これは従来のVisaトークン化技術の延長線上にあり、以下の特徴を持つ。

- そのエージェントの文脈でしか使えない(他のエージェントには流用できない)
- カード番号(PAN)を露出しない
- マーチャントのカテゴリ、利用期間、上限額などの制約を埋め込める
- ユーザーの認証済みインストラクションと、実際の決済認可をVisaNet側で照合できる

ユーザーは「ChatGPT用のVisaトークン」「Gemini用のVisaトークン」を別々に発行できる。一方をrevoke(無効化)しても、もう一方や元のカードには影響しない。

### Visa MCP Server: エージェント開発者向けの統合パス

個人的に最も注目しているのは、VisaがMCP(Model Context Protocol)サーバーを公式に提供している点だ。GitHubの `visa/mcp` リポジトリには、TypeScript製のMCPサーバー実装と、X-Pay Token認証 + Message Level Encryption(MLE)を使った直接API統合のサンプルが含まれている。

```typescript
// 概念的な利用イメージ
const tools = await stripeMcpClient.listTools();
// enroll-card, initiate-purchase-instruction,
// retrieve-payment-credentials などが提供される

await mcpClient.callTool('enroll-card', {
  cardholderId: userId,
  cardLastFour: '1234',
  agentId: 'agent-xyz'
});
```

つまり、エージェント開発者はMCP経由でVisaの決済機能を呼び出せるようになっている。既にMCPでエージェントを組んでいる開発者にとって、決済統合のハードルが大きく下がる。カードネットワークがここまで開発者フレンドリーに動いてきたのは、正直驚きがある。

### Visaの設計思想: 「このエージェントは本物か?」

ここまで見てくれば分かるように、Visaのアプローチの核心は次の問いに対する答えだ。

> このエージェントは本物か?(Visaが認可した正規のエージェントか?)

エージェントを事前登録し、PKIで識別し、署名で正当性を証明する。古典的な「身元保証ベースのトラストモデル」だ。インターネット黎明期に、ブラウザがTLS証明書でサーバーを認証したのと同じパラダイムである。

このアプローチの強みは、マーチャント側の実装負荷が軽いことだ。CDN(例: AkamaiはTAPに対応済み)で署名検証を済ませれば、マーチャントは新しいコードを書かずにエージェント決済を受け入れられる。一方の弱みは、新しいエージェントプロバイダーの参入障壁が高いこと。Visaへの登録プロセスを経ない限り「Trusted Agent」にはなれない。

---

## Mastercardのアプローチ: 意図をトークン化する

### Mastercard Agent Pay の全体像

Mastercardの解は、Visaとは正反対の方向に振り切っている。「エージェントが何者か」ではなく「ユーザーが何を指示したか」をトークン化するアプローチだ。

2025年4月29日、Visaの発表からわずか数週間後にMastercardが発表したのが「Mastercard Agent Pay」。その後、Citi、US Bankでのパイロットを経て、2025年11月までに全米のMastercardカードホルダーに展開された。技術的には、次の2つのポイントで成り立っている。

1. Agentic Tokens: エージェントごとに発行される、スコープ制限付きトークン
2. Verifiable Intent: ユーザーの購入意図そのものを検証可能にするフレームワーク

### Agentic Tokens: MDESの拡張

Mastercardは長年、MDES(Mastercard Digital Enablement Service)というトークン化基盤を運用してきた。Apple Pay、Google Pay、Click-to-Pay などで使われる、PANをトークンに置き換える仕組みだ。

Agentic Tokensは、そのMDESに対して2つの新しいフィールドを追加する形で実装されている。

- `agent_identifier`: どのエージェントが取引を開始したかを示す識別子
- `session_scope`: そのトークンが使える条件(上限額、マーチャントカテゴリ、有効期限など)

```json
{
  "token": "5413111111114000",
  "expiry": "12/28",
  "agent_identifier": "openai-chatgpt-prod",
  "session_scope": {
    "max_amount": 50000,
    "currency": "JPY",
    "merchant_categories": ["5411"],
    "expires_at": "2026-05-05T18:00:00Z"
  }
}
```

このトークンの重要な性質は、Mastercardの認可ネットワーク層でスコープが強制される点だ。エージェントが`session_scope`を逸脱した取引をしようとすれば、Mastercardネットワーク自身がそれを拒否する。エージェント開発者やマーチャント側でスコープ強制ロジックを書く必要はない。この「ネットワーク側で勝手にガードレールが効く」設計は、エージェント開発者にとってはかなり嬉しい。

加えて、`agent_identifier`が取引データに残ることで、紛争解決時にエージェント単位での責任追跡が可能になる。「ChatGPTで初期設定された買い物カートで30%のチャージバック率が出ている」といった分析が、ネットワーク側でできる。これがMastercardが「Trust Center for Agentic AI」と呼ぶ機能の中核だ。

### Verifiable Intent: 意図のトークン化

Agent Payのもう一つの要がVerifiable Intentだ。ユーザーの購入意図をデジタル契約(Intent Artifact)として暗号署名し、トークンと一緒にネットワークに流す仕組みである。

実装的には、GoogleのAP2プロトコルとほぼシームレスに連携する。AP2のIntent MandateやCart MandateをそのままMastercardのVerifiable Intent Artifactに変換できるため、AP2準拠のエージェントはMastercard Agent Payを「ほぼそのまま」使える。

```json
{
  "mandate_type": "CartMandate",
  "user_id": "did:example:user-abc",
  "merchant_id": "did:example:merchant-xyz",
  "items": [
    {"sku": "BIKE-001", "qty": 1, "price": 89000}
  ],
  "total": 89000,
  "currency": "JPY",
  "user_signature": "0x3045...",
  "signed_at": "2026-05-05T10:00:00Z"
}
```

ユーザーは自分のデバイス(典型的にはスマートフォンのSecure Enclave / TEE)に保管された秘密鍵で、このCart Mandateに署名する。これでネットワーク・イシュアー・マーチャントの誰もが「ユーザーがこの購入を承認したこと」を暗号学的に検証できる。

### Web Bot Auth と Cloudflare 連携

Mastercardはマーチャント側の実装負荷を下げるため、Web Bot Auth(IETF RFC 9421ベース)にも対応している。Cloudflareと提携し、CDN層でエージェント認証を済ませられるようにした。

ここで面白いのは、Visa TAPと同じRFC 9421を使っているのに、目的が異なる点だ。

- Visa TAP: エージェントの「正規性」を署名で証明
- Mastercard Web Bot Auth: マーチャントが「これはエージェントトラフィックである」と識別するため

つまり、署名技術は共通でも、何を保証するかが違う。

### Mastercardの設計思想: 「ユーザーは本当にこれを指示したか?」

Mastercardのアプローチを一言で言うと:

> ユーザーは本当にこの購入を指示したのか?(意図に署名されているか?)

エージェントの身元証明には踏み込まず、代わりにユーザーの意図を暗号学的に検証可能な形で取り出す。「意図ベースのトラストモデル」だ。

このアプローチの強みは、新しいエージェントが参入しやすいことだ。エージェントプロバイダーがMastercardに事前登録する必要はなく、AP2準拠の意図を生成できれば誰でもAgent Payに乗れる。一方の弱みは、Intent Artifactの生成が重いこと。3つのMandate(Intent / Cart / Payment)を生成・署名・検証するオーバーヘッドは、従来のCard-Not-Present認証よりも大きく、低額決済での経済性は議論の余地がある。

---

## 設計思想の対比: Visa vs Mastercard

ここまでの議論を整理する。

| 観点 | Visa Intelligent Commerce | Mastercard Agent Pay |
|---|---|---|
| コア質問 | このエージェントは本物か? | ユーザーは本当にこれを指示したか? |
| トラストモデル | 身元保証ベース(PKI) | 意図ベース(Mandate署名) |
| トークンの単位 | エージェント+ユーザー単位 | エージェント+セッション単位 |
| スコープ強制の場所 | エージェント側 + ネットワーク照合 | ネットワーク層で自動強制 |
| 新規エージェント追加 | Visaへの登録が必要(高負荷) | AP2準拠なら参入可能(低負荷) |
| Intent生成のコスト | 軽い(署名のみ) | 重い(3つのMandate) |
| 紛争解決のエビデンス | Commerce Signals + ID Token | Cart/Intent Mandate全体 |
| マーチャント側実装 | TAP署名検証(CDNで可) | Web Bot Auth(CDNで可) |
| 既存基盤との関係 | VisaNet + 新トークンタイプ | MDES + 2フィールド拡張 |
| AP2との相性 | 互換性あり(一部情報落ち) | ほぼロスレス変換可能 |

どちらが正しい、というよりは、問題空間を違う切り方で割っていると理解するのが正確だ。Visaは「インターネットのDNS+TLS的な世界」を再現しようとしており、Mastercardは「契約署名の世界」を作ろうとしている。

実務的な含意としては、両社のアプローチは補完的だ。Stripeは独自のSPT(Shared Payment Token)というプリミティブで、両社のagentic network tokenを抽象化して受け入れている(2026年3月発表)。マーチャントはStripeに繋ぐだけで、両ネットワークのエージェント決済を統一APIで受けられる。

---

## プロトコル戦争の全体地図

エージェント決済まわりは、すでにプロトコルがフラグメント化している。エンジニアとして全体地図を持っておく価値があるので、主要プレイヤーを整理する。

### 主要プロトコル一覧

- AP2(Agent Payments Protocol): Google主導、60社以上が参加。Mandate(Intent/Cart/Payment)による意図のトークン化が核。Mastercardと相性が良く、x402拡張でステーブルコイン決済にも対応。FIDO AllianceのAgentic Authentication Working Groupで標準化進行中
- ACP(Agentic Commerce Protocol): Stripe + OpenAI主導。チェックアウトのAPI仕様にフォーカス。MCP transportにも対応
- UCP(Universal Commerce Protocol): Google主導。Chromeブラウザ(シェア70%超)に組み込まれ、Geminiエージェントから利用される
- TAP(Trusted Agent Protocol): Visa主導、10社以上が共同策定。エージェント正規性の証明にフォーカス。Akamai対応
- MPP(Machine Payments Protocol): Stripe + Tempoブロックチェーン。マイクロペイメント・ストリーミング決済向け
- x402: HTTPネイティブの支払いプロトコル。AP2とのブリッジ拡張(`a2a-x402`)が存在
- Web Bot Auth: IETF RFC 9421ベース。Cloudflare、Mastercard、Akamaiが採用

### レイヤー別の整理

ここで重要なのは、これらのプロトコルが異なるレイヤーを担っていることだ。

```
┌──────────────────────────────────────────────────┐
│ エージェント間通信レイヤー                                │
│ A2A (Agent2Agent)、MCP                            │
└──────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────┐
│ コマースプロトコルレイヤー                                │
│ ACP / UCP / AP2                                  │
└──────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────┐
│ エージェント認証レイヤー                                  │
│ TAP / Web Bot Auth (両者ともRFC 9421ベース)         │
└──────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────┐
│ 決済クレデンシャルレイヤー                                │
│ Visa Agent Token / Mastercard Agentic Token /    │
│ Stripe SPT                                       │
└──────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────┐
│ 決済ネットワーク・ステーブルコイン                         │
│ VisaNet / Mastercard / x402(Tempo, Solana, etc.) │
└──────────────────────────────────────────────────┘
```

つまり、「Visa vs Mastercard」「ACP vs UCP vs AP2」のような二項対立は、実は同じレイヤー内の戦いではない。AP2とUCPは並列だが、AP2とTAPは別レイヤーで、組み合わせて使う前提だ。このレイヤー構造が見えると、ニュースの読み方が変わってくる。

### Stripeの抽象化レイヤー

Stripeは2026年4月のStripe Sessionsで、独自の抽象化レイヤーとしてSPT(Shared Payment Token)をさらに強化した。SPTは以下を吸収する:

- Visa Intelligent Commerce のagent token
- Mastercard Agent Pay のAgentic Token
- Affirm / Klarna のBNPL agent token

マーチャント側からは「Stripeに繋ぐだけ」で、これらすべてのエージェント決済を受けられる。プロトコル戦争の上位に立つ抽象化レイヤーを取りに行く、いかにもStripeらしい動きだ。

実際、Stripeの公式ブログによれば、Agentic Commerce SuiteはACP、UCP、AP2、MPPのすべてに対応する「protocol-agnostic commerce layer」として設計されている。

---

## エンジニアとして何をどう見るか

最後に、エンジニアとしてこの動向にどう関わるかを考える。

### 自社プロダクトでエージェント決済を受ける場合

ECサイトやSaaSを運営している立場なら、選択肢は3つある。

1. PSPに乗る: Stripe、Adyen、PayPal等のSPT対応PSPを使えば、両ネットワークのエージェント決済を統一APIで受けられる。実装負荷が最も軽い
2. CDNレイヤーで対応: CloudflareやAkamaiでWeb Bot Auth / TAPの署名検証を済ませる方法。マーチャント側コードはほぼ不変
3. 直接統合: Visa MCP Server、Mastercard MDES API、AP2 SDKを直接叩いて自前で組む。最も柔軟だが工数が大きい

2026年時点では、(1)PSPに乗るのが圧倒的に現実解だ。プロトコル仕様がまだ動いており、自前で組むと「zombie integration」(数ヶ月で陳腐化する実装)になるリスクが高い。

### エージェント側を作る場合

逆に、購入機能を持ったAIエージェントを作る立場なら、観点は変わる。

- AP2を起点に設計するのが筋がよい。Mandate生成・署名のロジックを実装すれば、Mastercard Agent Pay、PayPal、x402経由のステーブルコイン決済まで横展開できる
- Visa MCP Serverを使うと、TAPベースの決済を最短経路で組み込める。すでにMCPでエージェントを組んでいるなら統合は容易
- AP2のリファレンス実装はPython / TypeScript / Kotlin / Goで公開済み。`github.com/google-agentic-commerce/AP2` のサンプルを見れば、Cart Mandate / Intent Mandate / Payment Mandateの3層構造が具体的に分かる

### 日本の状況と当面の備え

日本でのエージェント決済は、米国に比べて少なくとも1年以上遅れている。GMOペイメントゲートウェイ、ソニーペイメント、楽天ペイなど主要プレイヤーは2026年Q2時点で目立った動きを見せていない。JCBはAP2の launch coalition に名を連ねているが、現状はsignal参加にとどまっている印象だ。

ただし、エンジニアとして今から触れる素材はある。

- RFC 9421(HTTP Message Signatures): TAPもWeb Bot AuthもこれがベースなのでRFCを読んでおく価値が高い
- AP2のSDK: Pythonサンプルを動かしてみると、Mandateチェーンの設計が体感できる
- Visa MCP Server: `visa/mcp` リポジトリを clone して動かせば、エージェント決済の API 呼び出し感覚が掴める

これらは英語ドキュメントが中心で、日本語の解説記事も少ないため、今のうちに触れておくと2027年以降に効いてくるはずだ。

---

## まとめ

カードネットワーク2社のエージェント決済への対応は、表面的には似て見えるが、内実は根本的に異なる設計思想で動いている。

- Visaは「エージェントを認証する」。PKIと署名でエージェントの正規性を担保し、登録制の安心感を提供する
- Mastercardは「意図をトークン化する」。MDESの拡張とMandate署名で、ユーザー意図を検証可能にする
- 両者は補完的で、Stripeのような抽象化レイヤーがそれを統合する

設計思想を理解しておくと、各種プロトコル(ACP / UCP / AP2 / TAP / MPP / x402)の関係性も整理しやすい。エージェントが経済主体として動き始める時代、決済インフラの土台がどう変わろうとしているかを掴んでおくことは、Web開発者にとっても有用な前提知識になるはずだ。

この分野は月単位で状況が変わる。新しい動きがあれば追記していくので、気になった方はフォローしておいてもらえると嬉しい。質問や「ここもっと掘り下げてほしい」があればコメント欄でぜひ。

---

## 参考リンク

https://developer.visa.com/capabilities/visa-intelligent-commerce

https://developer.visa.com/capabilities/trusted-agent-protocol/trusted-agent-protocol-specifications

https://github.com/visa/mcp

https://www.mastercard.com/global/en/news-and-trends/stories/2025/agentic-commerce-framework.html

https://ap2-protocol.org/specification/

https://github.com/google-agentic-commerce/AP2

https://stripe.com/use-cases/agentic-commerce

https://datatracker.ietf.org/doc/html/rfc9421
