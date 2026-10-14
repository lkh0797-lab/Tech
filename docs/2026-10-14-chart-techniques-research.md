# 문헌 조사 원문 (2026-10-14)

## candles

# Topic A research report: candlestick definitions for 적삼병 / Three White Soldiers, 장대양봉 / Long White, and 망치형 / Hammer

Researched 2026-10-14. Spec: `G:/내 드라이브/Claude/Tech/docs/2026-10-14-chart-techniques-design.md` (§1 `red_three_monthly`, §2 장대양봉 for `fib_pullback`, §3 바닥 망치형). Quotes are kept to short fragments (under 15 words) and the rest is paraphrased, with the source URL on each line.

Local extracts (session scratch folder, not kept — re-download from the URLs below):
- `<scratch>/research/kiwoom_AdvancedSearch.txt` — text of the official Kiwoom 영웅문4 조건검색 help PDF.
- `<scratch>/research/bulkowski_top10.txt` and `<scratch>/research/bulkowski_eightbest.txt` — text of two Bulkowski *Stocks & Commodities* articles from 2011.
- `<scratch>/research/topicA_source_log.txt` — page map.

## 0. Source access and quality
| Source | Status | Use |
|---|---|---|
| Bulkowski, thepatternsite.com (ThreeWhiteSoldiers, Hammer, LongWhiteDay, TallCandleSAR, TallCandleSetup, MinorHiLow, glossary) | fetched | primary for rules and stats on daily bars |
| Bulkowski, S&C V.29:6 "Top 10 Candles That Work" (Jun 2011) and V.29:11 "Eight Best-Performing Candles" (Fidelity reprints, https://fidelity.com/bin-public/060_www_fidelity_com/documents/Top10CandlesWork_620095.pdf and https://www.fidelity.com/bin-public/060_www_fidelity_com/documents/EightBestCandles.pdf) | fetched, pdftotext | methodology plus the "tall" definition |
| TA-Lib C source (https://github.com/TA-Lib/ta-lib, `ta_CDL3WHITESOLDIERS.c`, `ta_CDLHAMMER.c`, `ta_CDLLONGLINE.c`, `ta_global.c`, `ta_utility.h`) | fetched | the only codified numeric thresholds found; its comments cite Nison and Morris |
| StockCharts ChartSchool (bullish reversal patterns; pattern dictionary) | fetched | Hammer criteria, definition of a decline |
| Kiwoom 조건검색 개별조건 도움말 PDF (https://download.kiwoom.com/hero4_help_doc/KiwoomHero4_AdvancedSearch.pdf) | downloaded, pdftotext | official Korean HTS semantics |
| 한경 경제용어사전, 미래에셋 HTS 0544 help, 삼성증권 POP 1512 help | fetched | Korean definitions |
| Japanese brokers (野村 Nomura, iFinance, sevendata) for 赤三兵 (Sakata) | fetched | 사케다 적삼병 |
| **Nison book, verbatim** | **not reachable** (1library 403); content via secondary transcriptions only | flagged per row |
| **Investopedia** | **blocked** (crawler refused) | not used |
| 김정환《차트의 기술》(이레미디어, 2013 개정증보판) | only the table of contents was visible (yes24) | Part 7 is a candle chapter; **no "월봉 적삼병" entry is visible**, so the monthly rule cannot be checked against the book |

---

## A1. 적삼병 / Three White Soldiers (TWS)

### A1.1 What each source says
| Source | Definition (short quote or paraphrase) | URL |
|---|---|---|
| Bulkowski | Configuration (paraphrased): three tall white candles, each closing near its high, each close higher than the last, bodies overlapping. Each candle opens inside the prior body; "short upper shadow". Prior trend: **"Downward"**. | https://thepatternsite.com/ThreeWhiteSoldiers.html |
| Bulkowski, S&C 2011 | "The last two candles must open within the body of the prior candle." Tall means "taller than the average candle height over the past week or two." | Top10 PDF above |
| Nison (secondary: search snippet of a 1library book excerpt) | Three white candles with consecutively higher closes; each opens within or near the prior white body; each closes at or near its high. Seen as strength if it appears "at a low price area after a period of stable prices". | https://1library.net/article/advancing-white-soldiers-japanese-candlesticks-charting-techniques-steve.q50xglgz (403, snippet only) |
| TA-Lib | "three white candlesticks with consecutively higher closes"; "opens within or near the previous white real body"; "no or very short upper shadow"; "Greg Morris wants them to be long, Steve Nison doesn't"; "must not be far shorter than the prior candle" (to separate it from advance block) | https://raw.githubusercontent.com/TA-Lib/ta-lib/main/src/ta_func/ta_CDL3WHITESOLDIERS.c |
| Kiwoom, PDF p.39 | "각각의 시가가 전날의 몸통 안에서 형성되고 매일 새로운 고가를 형성". Treated as a reversal signal if it appears after "바닥권이나 일정기간 횡보 후". Close "거의 고가 부근". Also lists 어드밴스 블락 and 스톨드(정체 적삼병) as warning variants. Kiwoom files TWS under the section "상승추세가 지속되고 있는 캔들". | Kiwoom PDF |
| 한경 경제용어사전 | "종가가 시가보다 높게 형성되면서 양봉이 3일 연속". Monthly: "월간 기준으로 적삼병(석 달 연속 양봉이 나타나는 경우)" is read as entry into a trending bull market. **No higher-close or shadow condition.** | https://dic.hankyung.com/economy/view/?seq=5747 |
| 미래에셋 HTS | "시가, 고가, 종가가 연이어 상승"; a strong reversal signal if it appears in a downtrend | https://securities.miraeasset.com/kairos/0544.htm |
| 삼성증권 POP | "종가가 상승하는 양봉이 연속"; "윗그림자와 아래 그림자가 없거나 짧은 양봉 세 개" | http://www.samsungpop.com/contents/poptrading/help/1512.html |
| 赤三兵, Sakata (野村) | 3 bullish candles; "終値がいつもよりも切り上げている" (closes stepping up) | https://www.nomura.co.jp/terms/japan/a/akasanpei.html |
| 赤三兵 (iFinance) | "高値と安値を切り上げ" (higher highs and higher lows). No upper shadows means a strong buy; upper shadows lower reliability. 先詰まり = upper shadow on the 3rd candle; 思案星 = 3rd candle is a small 陽のコマ. | https://www.ifinance.ne.jp/learn/technical/twd068.html |
| 赤三兵 (sevendata) | "底値からの上昇パターン"; a weekly occurrence is seen as stronger than a daily one | https://www.sevendata.co.jp/pattern/kai/j.html |

**Bulkowski statistics** (US daily bars, 103 candle types; S&C 2011 says "daily price data", a database of 500 stocks over 10 years):
- "Bullish reversal 82% of the time".
- Overall performance rank 32 of 103; frequency rank 67.
- Only 593 of 3,333 samples broke out downward.
- Breakout means "a close above the top of the highest candle".
- Tips (paraphrased): the pattern is best read as an upward retrace inside a downtrend; ones near the top third of the yearly range "frequently act as reversals"; volume "gives performance clues".
- He calls a 6% move "a gift". Average moves after the pattern are small.

### A1.2 Where sources disagree
1. **Minimum definition.** 한경 requires only 3 consecutive 양봉 (close > open). Most other sources also require higher closes: Bulkowski, Nison, TA-Lib, 미래에셋, 삼성, 野村, and the daum cafe post.
   - Rising highs and lows: iFinance, 미래에셋, and Kiwoom's "매일 새로운 고가".
   - Open within the prior body: Bulkowski, Kiwoom. "Within or near" the prior body: Nison, TA-Lib.
2. **Body size.** Morris and Bulkowski want tall candles. Nison does not (per the TA-Lib comment). TA-Lib only requires that the 3rd body is not short and no body is far shorter than the one before.
3. **Upper shadow.** Bulkowski and TA-Lib make "short" a requirement. iFinance and sevendata treat it as a strength grade. 한경 does not mention it.
4. **Context.**
   - Bulkowski's inbound trend is "Downward".
   - Nison and Kiwoom: a low price area or bottom after consolidation (횡보).
   - 한경: during a correction period (조정기간).
   - Kiwoom nonetheless files TWS under trend continuation.
   - Bulkowski's data says patterns within a third of the yearly **high** frequently act as reversals. So "bottom only" is a Korean/Japanese convention that Bulkowski's daily statistics do not support.
5. **What counts as 양봉.** Kiwoom (p.3): "시가보다 종가가 높게 끝나며 상승으로 마감한 봉", i.e. strictly close > open. TA-Lib's white is close ≥ open, so a doji counts as white. Kiwoom keeps 상승/하락/보합 (versus previous close) separate from 양봉/음봉 in "기간내 등락봉수" (p.6), so 양봉 is not the same as "close above previous close".

### A1.3 Kiwoom "캔들연속발생 3봉 양봉" semantics
- Condition text (PDF p.7): "양봉이나 음봉이 연속적으로 발생한 종목 검색"; note: "1 봉연속 양봉 발생 검색 시 현재 양봉인 종목 조회".
- 양봉 means close > open on that bar (p.3). There is no higher-close, body-size or shadow condition. A doji (close = open) breaks the run.
- **Important (p.3):** 종가 is "봉이 끝나야 확정되는 가격, 캔들이 그려지는 중간에는 현재가가 종가가 됨". The rightmost candle is "0봉전". So a Kiwoom **monthly** search at 0봉전 includes the **in-progress month**, which conflicts with the spec's completed-months-only rule. Kiwoom "1봉전 기준" is the equivalent of the spec's rule.
- Confidence: high on close > open (official doc). Medium on Kiwoom's internal treatment of exact ties beyond the doji definition.

### A1.4 Monthly bar construction
- Open = open of the first business day; high and low = the month's extremes; close = close of the last business day. CSI Data says the same (paraphrased): first business day's open, the month's high and low, last business day's close. https://csidata.com/custserv/onlinehelp/OnlineManual/structureofdailyweeklyandmont.htm
- Volume: CSI says monthly volume "normally represent[s] the average daily volume", with the total optional. **The spec's sum is a valid but different convention.** Keep the sum and label it.
- Use split/bonus-adjusted daily data (수정주가) before grouping. Charts adjust history for corporate actions (Börse Frankfurt explanation: https://boerse-frankfurt.de/en/adjusted-prices). I found no KRX primary source, so the adjusted-data rule rests on the general practice.
- **Completed month (no look-ahead):** month M is complete once a daily bar from a later month exists, or when the as-of date is past M's last calendar day. Prefer the "later bar exists" test: it is prefix-invariant by construction. Implementation choice.
- Drop zero-volume suspended (거래정지) rows before grouping. No source found. Rationale: vendors often fill suspended days with the previous close, which would fake the monthly open or low.

### A1.5 Bottom area (바닥권) definitions found
| Definition | Source | Phrase |
|---|---|---|
| Lowest third of the yearly range; yearly range = "highest high and lowest low of the prior year" | Bulkowski glossary https://thepatternsite.com/glossary.html ; thirds: https://thepatternsite.com/buylow.html , https://www.thepatternsite.com/CandlestickTip.html | "within the lowest third of the yearly price range" |
| −20% from recent highs (bear-market convention, also applied to single stocks) | https://www.fool.com/investing/how-to-invest/bear-market.aspx | "typically defined as a 20% drop from recent highs" |
| Position within the period's high–low range (0% = at the low) | Kiwoom 기간내 주가위치, PDF p.6 | "0 과 가까울수록 … 최저가에 가깝고" |
| A low price area after stable prices or consolidation | Nison (secondary); Kiwoom p.39 "바닥권이나 일정기간 횡보 후" | — |

### A1.6 Proposed parameters for `red_three_monthly` (monthly bars)
| Param | Proposed value | Source(s) | Confidence | How to code on EOD, no look-ahead |
|---|---|---|---|---|
| `RTM_BULL` | strict `C > O` | Kiwoom p.3; 한경 | high | per completed month |
| `RTM_N` | 3 consecutive completed, calendar-consecutive months | 한경 "석 달 연속 양봉"; video | high | a calendar gap (no bar for a month) breaks the run (implementation choice) |
| `RTM_REQUIRE_HIGHER_CLOSE` | **True** (recommended addition) | Bulkowski, Nison, TA-Lib, 미래에셋, 삼성, 野村 | high (broad agreement); only 한경 omits it | `C[k] > C[k-1]` for the 2nd and 3rd months. On monthly bars it is almost always implied. |
| `RTM_OPEN_NEAR_BODY` | flag only (not required on monthly bars) | Bulkowski, Kiwoom "within"; Nison, TA-Lib "within or near"; TA-Lib Near = 0.2 × average high-low range of the prior 5 bars | medium | `O[k] >= O[k-1] and O[k] <= C[k-1] + 0.2*mean(H-L, 5 months before k-1)`. A monthly open ≈ the prior month's close, so this is nearly tautological. |
| `RTM_SHORT_UPPER` | flag: `(H-C) < 0.1*mean(H-L over the 10 prior months)` | TA-Lib ShadowVeryShort {HighLow, 10, 0.1}; Bulkowski "short upper shadow"; iFinance strength grade | medium (0.1 is TA-Lib's default, not Nison's) | needs 10 prior completed months; otherwise "모름" |
| `RTM_WARN_ADVANCE_BLOCK` | warn if month-3 body < month-2 body − 0.6 × average range of the prior 5 months, **or** month 3 has an upper shadow ≥ its body | TA-Lib Far {HighLow, 5, 0.6}; Kiwoom 어드밴스 블락 / 스톨드; iFinance 先詰まり / 思案星 | medium | flag only |
| `RTM_RISING_LOWS` | flag (enforces the spec's "no new low below the confirmed low") | iFinance; Kiwoom "매일 새로운 고가"; 미래에셋 | medium | `L[k] > L[k-1]` |
| `RTM_BOTTOM_DD` (spec `구현 선택`) | keep `L_low ≤ 0.80 × max(close of the prior 12 completed months)` | −20% convention (Fool); Bulkowski's yearly range uses highest high | medium (convention, not a candle-literature rule) | window = the 12 months before the low month, excluding it |
| `RTM_YEARLY_POS` (context) | report `(C_sig − LL12)/(HH12 − LL12)`; ≤ 1/3 = "연중 하단 ⅓" | Bulkowski thirds + glossary | high for the definition | HH/LL from the 12 completed months up to and including the signal month |
| `RTM_MAX_LAG` (spec "6개월 안") | 6 | **no source found — implementation choice.** Rationale: a cap only. The run must start right after the low, so the 3rd soldier is ≤ 3 months after the low anyway. | — | — |

**Pivot-low timing.** Month m is a confirmed low only after month m+1 completes. Soldiers can be m+1..m+3, so the earliest signal is at completion of m+3. The spec leaves open whether month m itself can count as soldier #1. I found no source either way.

### A1.7 Daily TWS (if a daily detector or the stats context is wanted) — codified (TA-Lib with Bulkowski)
Use averages over **prior** bars only, i.e. `shift(1).rolling(N)`. This follows TA-Lib and Bulkowski's "do not include today's candle".

```text
white_k   : C>O (strict, Kiwoom) for k = t-2, t-1, t
closes    : C[t] > C[t-1] > C[t-2]
opens     : O[k] > O[k-1] and O[k] <= C[k-1] + 0.2*avgRange5[k-1]      for k = t-1, t
upper     : (H-C)[k] < 0.1*avgRange10[k]                                  for all 3
not_far   : body[k] > body[k-1] - 0.6*avgRange5[k-1]                     for k = t-1, t
not_short : body[t] > avgBody10[t]
Bulkowski 'tall' option: body[k] > mean(|body|, prior 5..10 bars) for all 3   (S&C 2011)
signal date = t (close of 3rd candle); 'breakout' = later close > max(H[t-2..t]) (Bulkowski)
```

---

## A2. 장대양봉 / Long White Day (spec §2 baseline: "종가 등락 ≥ +7% 이고 거래량 ≥ 20일 평균 × 2")

### A2.1 Definitions found
| Source | Rule | URL |
|---|---|---|
| Bulkowski, Long White Day | body at least 3× the average body height of the last 2–3 weeks (paraphrased); "shadows shorter than the body"; no trend required; "Continuation 58% of the time"; overall rank 53 | https://thepatternsite.com/LongWhiteDay.html (same rule in the S&C Eight Best article) |
| Bulkowski, tall candle S/R test | bodies "more than twice as tall as the prior 22 trading day average" (body = open to close) | https://thepatternsite.com/TallCandleSAR.html |
| Bulkowski, tall candle setup | high–low range vs the average of the "preceding 22 trading days" "(do not include today's candle)". Threshold "more than 146% above the average" — **wording is ambiguous** (1.46× or 2.46×). MinorHiLow calls 146% "the median for tall candles", so read it as **1.46×**. | https://thepatternsite.com/TallCandleSetup.html , https://www.thepatternsite.com/MinorHiLow.html |
| Bulkowski, S&C 2011 | "tall" = "taller than the average candle height over the past week or two" | Top10 PDF |
| TA-Lib | BodyLong = body > 1.0 × average body of 10 bars; BodyVeryLong = 3.0 ×; LongLine also requires both shadows < ShadowShort (the 10-bar average shadow) | ta_global.c, ta_CDLLONGLINE.c |
| Kiwoom p.31 | 롱 바디 = open-to-close move "이전 날들의 캔들 몸통보다 긴 것" (no number). The 패턴정의 tool measures body as `|O−C|/전일종가*100` or relative to the previous body. | Kiwoom PDF |
| 미래에셋 | "시가 대비 종가의 상승폭이 큰 경우"; body much longer than recent bodies; no number | miraeasset 0544 |
| Korean convention (blog, low authority) | "7% 이상" used when the limit was 15%; with the 30% limit "10% 혹은 15% 이상" | https://i-whale.com/entry/기준봉이란-기준봉-선정하고-매매-종목-찾기 |
| Korean convention (blog) | "보통은 … 10~15% 이상 상승한 경우"; tails absent or short | https://jungbosum.com/주식-공부-차트-보는-법-장대양봉-역망치/ |
| Price-limit regime | ±15% became ±30% on **2015-06-15** | https://www.etoday.co.kr/news/view/1127429 |

**Disagreements:**
- Measurement base: open→close body (미래에셋, Kiwoom, Bulkowski) versus previous close→close 등락률 (the spec and the blogs). A +7% gap-up close with a small body counts under the spec but not under the HTS or Bulkowski definitions.
- Multipliers and windows differ: 3× over 2–3 weeks, 2× over 22 days, 1.46× range over 22 days, and TA-Lib's 1× or 3× over 10 bars.
- The Korean % convention is regime-dependent (the 2015 limit change).

### A2.2 Proposed parameters
| Param | Proposed | Source | Confidence | EOD coding |
|---|---|---|---|---|
| `LB_WHITE` | `C > O` | 미래에셋, Kiwoom | high | — |
| `LB_BODY_REL_K`, `LB_BODY_REL_N` | body `(C−O) ≥ 3.0 × mean(|C−O|)` over the **15 prior bars** | Bulkowski "three times … last 2 or 3 weeks". N = 15 is the implementation choice (3 weeks ≈ 15 sessions; 10 is also defensible). Fallback 2.0 × / 22 bars (TallCandleSAR) if hits are too rare. | high for the rule; medium for N | `abs(C-O).shift(1).rolling(15).mean()`; skip zero-volume (suspended) bars when averaging (implementation choice) |
| `LB_SHADOWS` | `(H−C) < (C−O)` and `(O−L) < (C−O)` | Bulkowski "shadows shorter than the body"; Korean blogs: tails short or absent | high | same bar |
| `LB_MIN_CHG` (spec) | keep `C/C[t-1] − 1 ≥ 0.07` as a Korean-convention gate; offer 0.10 as an option | i-whale (7% in the 15%-limit era; 10–15% now); jungbosum (10–15%) | low–medium (blog-level) | — |
| volume ×2 of the 20-day average | keep, but mark **no source found for "×2"**. i-whale defines heavy volume only as above an arbitrary-period average. | — | — | use the 20 prior bars only |

The relative body test (`LB_BODY_REL`) makes the rule robust across the 2015 limit change and across large- versus small-cap volatility. The % gate alone is not.

---

## A3. 망치형 / Hammer (spec §3: "아래꼬리 ≥ 몸통 × 2, 위꼬리 짧음", within 20 bars before the breakout)

### A3.1 Definitions found
| Source | Rule | URL |
|---|---|---|
| Nison (secondary transcriptions; book not reachable) | real body at the upper end of the range, color unimportant; lower shadow twice the body; "no, or a very short, upper shadow"; must follow a decline | https://forums.babypips.com/t/the-traders-arms-2nd-floor/46232?page=13 ; https://mobee.com/en/mobee-academy/blog/hammer-artinya |
| StockCharts | "at least twice the length of the body"; "small or nonexistent upper shadow"; range "large relative to range over the last 10-20 days"; confirmation "within 1 to 3 days". A decline can be judged by price "trading below its 20-day exponential moving average" or by lower peaks and troughs. | https://chartschool.stockcharts.com/table-of-contents/chart-analysis/candlestick-charts/candlestick-bullish-reversal-patterns |
| Bulkowski | prior trend "Downward"; lower shadow "two or three times the height of the body"; "little or no upper shadow"; "Bullish reversal 60% of the time" (he notes this is near random); overall rank 65 of 103; frequency rank 36; best "within a third of the yearly low"; white-bodied hammers do best | https://thepatternsite.com/Hammer.html |
| TA-Lib | body short (< 10-bar average body); lower shadow > 1.0 × **own body** (ShadowLong {RealBody, 0, 1.0}); upper < 0.1 × 10-bar average range; "body below or near the lows of the previous candle" (Near = 0.2 × 5-bar average range) | ta_CDLHAMMER.c, ta_global.c, ta_utility.h |
| Kiwoom p.35 | named "해머(**양봉** 망치형)"; upper shadow almost none, lower shadow very long; at the bottom in a falling market | Kiwoom PDF |
| 한경 | "작은 몸통과 긴 아랫그림자"; upper shadow "전혀 없거나 거의 없는"; color generally irrelevant, but a 양봉 body is stronger; confirm with later price action | https://dic.hankyung.com/economy/view/?seq=10062 |
| 삼성 POP | shadow categories "몸통의2배이상 / 0.5배이하"; (hanging man) body "장중 거래 범위의 약 30-50이하"; "5-10일 정도의 상승추세 후" (the mirror case gives the trend window) | samsungpop 1512 |

**Disagreements:**
- Shadow ratio: 2× (Nison, StockCharts), 2–3× (Bulkowski), > 1× (TA-Lib default).
- Color: unimportant (Nison) versus white is better (Bulkowski, 한경) versus Kiwoom's naming "양봉 망치형".
- Where the body sits relative to the previous candle: TA-Lib says "below or near the lows of the previous candle". TrendSpider's help says "above or near the highs", which is probably an error (https://help.trendspider.com/kb/automated-technical-analysis/auto-recognized-traditional-candlestick-pattern-definitions).

### A3.2 Proposed parameters
| Param | Proposed | Source | Confidence | EOD coding |
|---|---|---|---|---|
| `HM_LOWER_X` | `lower ≥ 2.0 × body` | Nison, StockCharts, Bulkowski (lower bound of 2–3×), 삼성 2× category | high | `lower = min(O,C) − L`; `body = |C−O|`; require `H > L` |
| `HM_UPPER` | `upper ≤ 0.1 × mean(H−L, 10 prior bars)` | TA-Lib ShadowVeryShort (formalizes "little or no") | medium (TA-Lib's number) | `(H-L).shift(1).rolling(10).mean()`. Alternative: ≤ 10% of the bar's own range (no source). |
| `HM_RANGE_REL` | `(H−L) ≥ 1.0 × mean(H−L, 10 prior bars)` | StockCharts "large relative to range over the last 10-20 days". 1.0 × is the implementation choice. | medium | stops tiny-range bars from qualifying |
| body small / at the top | implied by the two rules above: body ≤ ~⅓ of the range, consistent with 삼성's "30-50 이하" | — | — | no extra test |
| `HM_PRIOR_DECLINE` | `C[t-1] < EMA20[t-1]` | StockCharts 20-day EMA; Bulkowski "Downward". Optional TA-Lib local test: `min(O,C)[t] ≤ L[t-1] + 0.2×mean(H−L, 5 prior)`. | medium | yesterday's values only |
| `HM_BOTTOM` | `(C − LL252)/(HH252 − LL252) ≤ 1/3`, HH/LL over bars t−251..t | Bulkowski "within a third of the yearly low"; yearly range = prior-year highest high and lowest low | high for the definition; medium for using the close as the reference | including bar t is legitimate (known at the close) |
| `HM_WHITE` | flag/score only, not required | Bulkowski, 한경, Kiwoom naming vs Nison | medium | `C > O` |
| `HM_CONFIRM` | status "확인" once some `C[t+k] > H[t]` for k = 1..3; "대기" before that | StockCharts 1–3 days; Bulkowski's breakout = close above the candle top | medium | prefix-safe: status at time T uses bars ≤ T only |
| doji (body = 0) | allowed; label "doji-hammer" (dragonfly) | TA-Lib's formula also admits it; Kiwoom describes the dragonfly doji as a bottom reversal | — | implementation choice |
| spec window "20봉 안" | keep | **no source found — implementation choice** | — | — |

---

## A4. Statistics and evidence caveats (for screen copy)
- Bulkowski's figures are on **US daily** data:
  - TWS: 82% bullish reversal, rank 32/103.
  - Hammer: 60% bullish reversal, rank 65/103.
  - Long White Day: 58% continuation, rank 53/103.
- These are breakout-direction rates, not returns. They do not transfer to KRX monthly bars.
- Academic counter-evidence: Marshall, Young & Rose (J. Banking & Finance 30(8), 2006). The Massey thesis abstract (DJIA stocks, 1992–2002) finds no evidence that following candlestick analysis beat the market (paraphrased) (https://mro.massey.ac.nz/handle/10179/1604 ; journal record: https://ideas.repec.org/a/eee/jbfina/v30y2006i8p2303-2323.html).
- No KOSPI-specific academic test of 적삼병 or 망치형 was found.
- This supports the spec's rule of not showing anecdotal returns, and of measuring results on our own data.

## A5. Recommended spec edits (summary)
1. §1: add `higher closes` as required (near-universal in the sources). Add `open-near-body`, `short upper`, `rising lows` and `advance-block/先詰まり` as flags. Document that Kiwoom's 0봉전 monthly search includes the in-progress month.
2. §1 바닥권: keep −20% (cite the convention). Add Bulkowski yearly-range position as context. Note that Bulkowski's daily data shows TWS also reverse near yearly highs.
3. §1 monthly volume: the sum is fine; note CSI's average-volume convention. Build months from adjusted daily data and drop suspended rows.
4. §2 장대양봉: add the body-relative test (≥ 3 × the 15-bar average body, Bulkowski) and shadows shorter than the body. Keep +7% as a Korean-convention gate (low confidence; 10% option). Mark volume ×2 as unsourced.
5. §3 망치형: lower ≥ 2 × body; upper ≤ 0.1 × the 10-bar average range; range ≥ the 10-bar average; prior close below EMA20; yearly-range position ≤ ⅓; color as a flag; optional 1–3-day confirmation.
6. Everywhere: every rolling statistic uses `shift(1)`; signals are dated at the bar that completes the pattern; confirmations are separate, later-dated events.


## fib

# Topic B: Fibonacci retracement research report (for `fib_pullback`, `trendline_fib`, `day_leader` and the market-context panel)

Spec read: `G:/내 드라이브/Claude/Tech/docs/2026-10-14-chart-techniques-design.md` (section 2 `fib_pullback`, section 4, section 5, and the market-context line about 김종봉 and KOSPI 50–61.8%).
Source log (paraphrased notes plus all numbers): `<scratch>/research/topicB_fib_sources.txt` (session scratch, not kept)
Kiwoom 조건검색 help PDF converted to text: `<scratch>/research/kiwoom/adv.txt`

Copyright note: supporting statements below are paraphrased. The report contains one verbatim quote (a Kiwoom formula string). Numbers and level names are facts, not quotes.

---

## A. Read this first: what the evidence says about Fibonacci levels

1. **Practitioner references present the levels as places to watch, not as signals.** StockCharts ChartSchool lists four common retracements: 23.6, 38.2, 50 and 61.8%. It calls them alert zones for a possible reversal and says other signals (candles, volume, momentum, moving averages) are needed to confirm one. The 50% level is not a Fibonacci ratio; it comes from Dow Theory's observation that the averages often give back about half of a move.
2. **Systematic tests find no special effect at these levels.**
   - **Bulkowski, automated test (2020):** 489 stocks, bull market 2009–2020, swing windows of 2, 5, 10 and 20 bars. Retraces of 38, 50 and 62% were no more likely than any other value from 1% to 100%. His earlier hand-picked sample had peaks at 50% and 61%; those disappeared in the automated test. (thepatternsite.com/SwingSetup.html)
   - **Bulkowski, manual sample:** median retrace 59%. About 55% of retraces end at or above the 61% level, so roughly 45% go deeper. About 25% go deeper than 72%. (thepatternsite.com/fib.html)
   - **Tsinaslanidis, Guijarro and Voukelatos (Expert Systems with Applications 187, 2022), DJIA, NASDAQ and DAX:** wider zones around a level catch more bounces simply because they are wider. Price behaviour in Fibonacci zones did not differ statistically from non-Fibonacci zones.
3. **What this means for the scanner:**
   - Present levels as "관심 구간" (zones of interest), never as a probability.
   - Make confirmation (candle plus volume) mandatory.
   - Never tune the touch tolerance to maximize hit rate.
   - This matches the spec's rule against showing example returns as if they were probabilities.

---

## B. Parameters, in spec section 2 order

### B1. Retracement levels
- **Proposed:**
  - Compute r = 0.236, 0.382, 0.5, 0.618 and 0.786.
  - Buy-eligible levels: {0.236, 0.382, 0.5}.
  - 0.618 is displayed and used for invalidation.
  - 0.786 is display only, labelled as a deep level, behind a config flag.
- **Sources:**
  - ChartSchool Fibonacci Retracements (chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-annotation-tools/fibonacci-retracements): the four common levels, 50% from Dow Theory.
  - StockCharts mailbag, 2009 (stockcharts.com/articles/mailbag/2009/05/using-the-fibonacci-retracements-tool.html): 23.6 is shallow (flags), 38.2–50 is moderate, 61.8 is deep.
  - tilnote summary of the same video (tilnote.io/pages/689b046edf13c4ef330e3e39): buy candidates are 23.6, 38.2 and 50; 61.8 is drawn but excluded from buys; 50% is singled out.
  - 0.786: not in ChartSchool. The Elliott Wave International tutorial (republished at marketcalls.in/trading-lessons/learn-how-to-apply-fibonacci-retracements-to-your-trading.html) says second waves commonly retrace .618 and also .786. The derivation of 0.786 as the square root of 0.618 appears only in secondary sources.
- **Confidence:** high for 23.6–61.8; medium for 78.6.
- **EOD coding:**
  - `level(r) = H - r*(H - L)`, using the high of the H bar and the low of the L bar (wick to wick). ChartSchool's ZigZag page says candlestick charts measure swings from the high-low range.
  - Compute the levels only once H is confirmed (B3), then freeze H and L for the life of the setup.

### B2. Trigger leg: 장대양봉 (spec: close-to-close ≥ +7% and volume ≥ 20-day average × 2)
- **Proposed:**
  - Keep +7% and ×2 as config values, marked as implementation choices.
  - Add a relative-body option that follows Kiwoom's definition: today's body is at least the largest body of the previous N bars. N is an implementation choice; 10 is suggested.
- **Sources:**
  - Kiwoom Hero4 조건검색 help PDF (download.kiwoom.com/hero4_help_doc/KiwoomHero4_AdvancedSearch.pdf): a 장대봉 is a candle whose open-to-close range is longer than the bodies of the preceding days. It gives no fixed percent.
  - Bulkowski measures "high volume" against a 30-day average (thepatternsite.com/pullbacks.html). That is a different convention from the spec's 20 days.
  - **No source found** for +7% or ×2.
- **Confidence:** low for the numbers; medium for the concept.
- **EOD coding:**
  - For ratio tests ("×k average"), use the average of the prior bars only (t−20 to t−1), so today's spike does not inflate its own baseline. This is an implementation choice.
  - Everything needed is known at the close of bar b.

### B3. Confirming the swing high H
- **Proposed default (follows the video):**
  - The candidate H is the highest high from the 장대양봉 bar onward.
  - H is confirmed at the first later bar c where `high_c <= H.high` and either `close_c < open_c` (음봉) or `close_c < close_{c-1}` (종가 하락).
  - If any bar's high exceeds H before confirmation, that bar becomes the new candidate.
  - If a new higher high appears after confirmation but before a buy signal, reset the setup.
- **Stricter option (config `swing_confirm = video | fractal2`):** the Williams fractal. The middle bar's high is above the highs of the 2 bars on each side, so the swing is known 2 bars later. BabyPips uses the same two-on-each-side rule.
- **Sources:**
  - The video rule appears only in the spec's own summary [19:00–20:00]. tilnote says only that the high must be confirmed, with no bar rule.
  - MetaTrader 5 fractals help (metatrader5.com/en/terminal/help/indicators/bw_indicators/fractals).
  - Bulkowski, SwingSetup: tested windows of 2, 5, 10 and 20 bars.
  - Kiwoom PDF: 음봉 means close below open.
- **Confidence:** medium.
- **EOD coding:**
  - H is usable only from bar c onward. A touch or signal may occur on bar c itself, because the confirmation is already known at that close.
  - Prefix-invariance test: add future bars and check that the confirmation bar c does not move.

### B4. Swing low L
- **Proposed:**
  - L is the lowest low between the bar after the last confirmed swing high (fractal-2) before the 장대양봉 and the 장대양봉 bar itself, capped at 60 bars. This is the trough the leg started from.
  - Fallback: the spec's lowest low within 60 bars.
  - Option: the last ZigZag trough at a 5% threshold.
  - Optional leg-size filter, off by default: `H/L - 1 >= 20%`.
- **Sources:**
  - tilnote: draw from the low before the 장대양봉 to the 장대양봉 high.
  - ChartSchool ZigZag (chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/zigzag): 5% is the traditional threshold, and StockCharts can auto-select one per security (examples 3.75% and 7.81%).
  - Bulkowski, SwingSetup: the best swing setups had rises of 21–38%.
  - **No source** for the 60-bar cap or for the 20% filter (20% is set at the lower end of Bulkowski's best bucket).
- **Why not the plain 60-bar minimum:** it can latch onto an older, deeper low that is unrelated to the impulse, which inflates the range and pushes the levels too low.
- **Confidence:** low to medium.
- **EOD coding:** uses only bars up to the 장대양봉 bar b.

### B5. What counts as "holding" a level (spec ±1.5%)
- **Proposed:**
  - Keep tol = 1.5% as a config value.
  - A touch on bar t requires `low_t <= level*(1+tol)`, `close_t >= level`, and `low_t > next_deeper_level` (otherwise it is a stop or a deeper-level event).
  - The active level is the deepest buy-eligible level touched during the pullback.
  - Optional ATR variant: `tol_t = max(1.5%, 0.5*ATR14_{t-1}/close_{t-1})`.
- **Sources:**
  - **No authoritative numeric tolerance found.**
  - Bulkowski (pullbacks page) says price returns to or comes close to a level and leaves "close" to judgment.
  - Kiwoom expresses nearness as a user-set ±N% band (근접률).
  - Tsinaslanidis et al.: wider zones raise bounce counts mechanically.
- **Rationale:** a fixed, modest band. Do not optimize it.
- **Confidence:** low; implementation choice.
- **Why close-basis versus intraday-basis matters:** in the KOSPI 2022 case (section D), the 2022 closing low sat 0.37% below the close-basis 61.8% line, and the intraday low was 1.0% below the intraday-basis line. A strict close rule would have ruled the case invalid; a ±1.5% band would have counted it as holding.

### B6. Buy signal: rebound 양봉 with volume through the 5-day volume average, entry at that close
- **Proposed default (follows Kiwoom's semantics):**
  - 양봉: `close_t > open_t` (Kiwoom's definition).
  - `MA5_t = mean(V_{t-4..t})`, which includes today. That is the standard Kiwoom moving average; its help text also ranks by a 5-day average volume that includes today.
  - "뚫는" (breaking through) is coded as a cross: `V_t > MA5_t` and `V_{t-1} <= MA5_{t-1}`. Kiwoom's own example for "today's volume breaks above the N-day average volume" is the condition `"[일] 0봉전 1이평 20이평 골든크로스"`.
  - Config option for a level-only test: `V_t > MA5_t`, without the cross.
- **Math note:** with today included, `V_t > MA5_t` is equivalent to `V_t > mean(V_{t-4..t-1})`, the average of the previous 4 days. An exclusive variant would use `mean(V_{t-5..t-1})`.
- **Optional "rebound" check:** `close_t > close_{t-1}`. ChartSchool counts a high-volume advance as a form of bullish confirmation and expects confirmation within 1–3 days.
- **Signal window:** the signal must come within 3 bars of the last touch. This is an implementation choice based on ChartSchool's 1–3 day window.
- **Other confirmations, behind flags:**
  - Hammer at the level. Bulkowski (thepatternsite.com/Hammer.html): lower shadow 2–3 times the body, little or no upper shadow, prior downtrend; it reverses about 60% of the time. ChartSchool requires at least 2 times the body.
  - Bullish engulfing. Bulkowski (thepatternsite.com/BullEngulfing.html): about 63% reversal.
  - ChartSchool's own example is a hammer on high volume at about 62%, followed by a breakout.
- **Stricter volume option:** pocket pivot (Morales and Kacher): `V_t > max volume of down days in t-10..t-1`. This comes from secondary sources (TradingView scripts citing *Trade Like an O'Neil Disciple*), so confidence is medium.
- **Entry:** close of bar t. tilnote says the buy order goes in at the signal candle's close. This is executable in practice: KRX's after-hours closing-price session (장후 시간외 종가) runs 15:40–16:00, with orders accepted from 15:30, at the day's close (Kiwoom help 1337, 다올 and 한국투자 terms).
- **Confidence:** medium-high for the definitions; medium that a cross is what the video meant.

### B7. Stop
- **Proposed:**
  - Primary stop: the next deeper line (23.6→38.2, 38.2→50, 50→61.8), as in the spec.
  - Also display: the swing-low stop (L), −7% from entry, and Bulkowski's 5% below the retrace low.
- **Sources:**
  - BabyPips, placing stops with Fibonacci (babypips.com/learn/forex/placing-stops-with-fibs):
    - Method 1 puts the stop just past the next Fibonacci level, which matches the spec exactly.
    - Method 2 puts it below the recent swing low, which gives more room but needs a smaller position.
  - MarketSmith India (O'Neil affiliate) on tradingqna.com: cut losses at 7–8%.
  - Bulkowski, SwingSetup: stop 5% below the low.
  - Bulkowski, fib.html: a stop no closer than a 67% retrace would have survived about 2 of 3 trades.
  - tilnote: stop on a break of 38.2 or 50, or of the 5-day or 10-day line.
- **Confidence:** high that next-level stops are a published convention; low for the fill model.
- **EOD coding (implementation choice):**
  - For bars after the entry bar, the stop is hit if `low_t < stop`.
  - Fill at `min(open_t, stop)` to model gap-downs.
  - Optionally offer a close-basis variant.
- **Caveat:** with a median retrace of 59%, next-line stops from 23.6 or 38.2 entries will often be hit. Show this as risk, not as an edge.

### B8. Invalidation
- **Proposed:**
  - A close below the 61.8% line, or any low below L.
  - Optional deep mode (config): invalidate at 78.6% instead of 61.8%.
- **Sources:**
  - Academic implementation (pmc.ncbi.nlm.nih.gov/articles/PMC8752186): the long position exits when price crosses below 61.8%. It uses levels 23.6–78.6 and enters on a cross back above 23.6.
  - Elliott hard rule (Kennedy/EWI, via MoneyShow): wave 2 never retraces more than 100% of wave 1. That is the L break.
  - Bulkowski data: roughly 45% of retraces go deeper than 61%, so this rule throws away many turns that eventually work. That is consistent with an entry rule limited to 23.6–50.
- **Confidence:** medium.

### B9. Stage labels
- **Approaching (spec: within 3% above a line):** **no source found**; implementation choice.
- **Signal day:** as in B6.
- **Extended (spec: more than +5% above the signal close):** analogous to the O'Neil/IBD 5% buy zone. Above 5% from the buy point a stock counts as extended, and the 5% leaves room for normal pullbacks inside the 7–8% stop (MarketSmith India post). Code it as `close_t > entry*1.05`. Confidence: medium.

### B10. ZigZag, if used for L or for trendline swings
- **Definition:**
  - 5% is the traditional default.
  - It is measured high-low on candlestick charts.
  - The last leg is provisional and drawn in hindsight (ChartSchool).
- **No look-ahead:** use only legs whose reversal has already exceeded the threshold as of bar t. The percent is a convention; keep it as config.

### B11. `day_leader` intraday Fibonacci
- Same formula, applied to the day's low and high.
- **Caveat (logic, no source):** a daily bar does not say whether the low came before the high. On a +10% 양봉 from the open, the low probably came first, but that is not guaranteed. Label the values as reference prices (참고가), as the spec already does.

### B12. Exit plan (common section): the Morales 10-day line rule
- A violation is a close below the 10-day line followed the next day by trading below that first day's low. This is how the spec already states it.
- **Source:** secondary. TradingView "7 Week Rule" scripts citing Gil Morales, *Trade Like an O'Neil Disciple*.
- **Confidence:** medium.

---

## C. Where sources disagree

1. **Whether the levels matter.** ChartSchool, BabyPips and EWI treat them as useful zones that need confirmation. Bulkowski's 2020 test and Tsinaslanidis et al. find no special clustering or bounce effect.
2. **How deep to buy.**
   - The video/tilnote favours 23.6–50 (with 50 emphasized).
   - Bulkowski's best swing results came with retraces of 45–75%.
   - EWI says wave 2 commonly reaches .618, while wave 4 is .382.
3. **Where to put the stop.** Next level (BabyPips method 1), swing low (method 2), 5% below the low (Bulkowski), at least 67% of the move (Bulkowski fib page), 7–8% (O'Neil), or the 5-day/10-day line (tilnote).
4. **How to confirm a swing.** One bar (video), 2+2 bars (fractal, BabyPips), or windows of 2–20 bars (Bulkowski).
5. **Volume baseline.** 5-day average (video, Kiwoom style), 30-day (Bulkowski), 50-day (IBD convention; not verified on investors.com, which could not be fetched), or pocket pivot (down-day maximum over 10 days).
6. **Index 50%.**
   - Dow Theory: secondary moves retrace one-third to two-thirds, with 50% typical (ChartSchool Dow Theory page, citing Hamilton). This is documented.
   - The 김종봉 claim **could not be found** in public material for 《돈의 시나리오》 (ridibooks or kyobo listings). Those show only that chapter 2 uses the index as a scenario tool.
   - The video summary's phrase "지수가 절반 이상 하락하면 매수 타이밍" (tilnote) is ambiguous. It could mean a 50% drawdown or a 50% retracement.
   - Attribute it only as "the video says 김종봉 emphasizes 50%".

---

## D. KOSPI facts (computed; not predictive, n = 2 cases)

### Case 1: 2020–2022 (rally, then the 2022 low)

| Item | Intraday basis | Close basis |
|---|---|---|
| Low (2020-03-19) | 1439.43 [brunch.co.kr/@35e8cb4b4cac47c/35] | 1457.64 [= 1566.15 − 108.51, Asia Economy, 2020-03-20] |
| High | 3316.08 on 2021-06-25 [mt.co.kr, 2025-09-10] | 3305.21 on 2021-07-06 [ajunews] |
| 50% level | 2377.76 | 2381.43 |
| 61.8% level | 2156.31 | 2163.41 |
| 2022-09-30 low [blockmedia 260213] | 2134.77 | 2155.49 |
| Retracement at that low | 62.95% | 62.23% |
| Distance from the 61.8% line | 1.0% below | 0.37% below |

- After that low, KOSPI rebounded to about 2483 on 2022-11-11, roughly +15% [biz.newdaily.co.kr, 2022-12-29].
- **Fact you can state:** the 2022 low landed at about 62–63% of the 2020–21 rally, a hair beyond 61.8%, inside or at the edge of the 50–61.8% band.

### Case 2: 2025–2026 (rally, then the July 2026 crash)

| Item | Intraday basis | Close basis |
|---|---|---|
| Low (2025-04-09) | 2284.72 [local cache] | 2293.70 [blockmedia 886879] |
| High | 9385.59 on 2026-06-19 [bullstory; cache] | 9114.55 on 2026-06-22 [Hanwha report via stock.pstatic.net; cache] |
| 50% level | 5835.15 | 5704.12 |
| 61.8% level | 4997.25 | 4899.26 |
| Crash low | 5262.77 on 2026-07-29 [kbmaeil, 2026-07-29] | 5593.56 on 2026-07-30 [cache] |
| Retracement at the crash low | 58.06% | 51.62% |
| Drawdown from the high | −43.9% | −38.6% |

- The 7-29 close was 5663.24, and circuit breakers fired on two consecutive days [kbmaeil, 2026-07-29].
- The rebound reached a high of 7216.62 on 2026-08-18, +37% from the intraday low [cache].
- As of 2026-10-13: close 6035.35 (45.1% retrace, close basis), intraday low 5911.11 (48.9%, intraday basis) [cache].
- **Cache coverage:** the local cache `G:/내 드라이브/Claude/Tech/cache/ohlcv/KOSPI.pkl` covers only 2023-08-24 to 2026-10-13, so it cannot check the 2020–22 case.

### 2007–08 (only partly verifiable)
- High 2085.45 intraday on 2007-11-01; closing high 2064.85 on 2007-10-31 [mt.co.kr, 2011-01-03].
- Low 892.16 intraday on 2008-10-27; close 938.75 on 2008-10-24 [mt.co.kr, 2008-10-31].
- Drawdown: −57.2% intraday, −54.5% close. The index more than halved.
- The 2003 starting low could not be verified, so no retracement figure is given.

### What the market-context panel should show
- Both the drawdown from the peak and the retracement of the last confirmed up-leg, on both close and intraday bases.
- A 50–61.8% band flag.
- No rebound probability.
- How the index swing anchor is chosen (for example a large ZigZag threshold) is an implementation choice; no source found.

---

## E. No-look-ahead state machine for `fib_pullback` (per stock; every rule uses only bars up to t)

1. `TRIGGER` at bar b: the B2 conditions hold. Fix L by B4.
2. `CANDIDATE`: track the highest high since b. When B3 holds at bar c, the setup is `CONFIRMED`: compute and freeze the levels.
3. For each bar t ≥ c:
   1. If a new high is above H, reset to `CANDIDATE`.
   2. If the close is below the 61.8% line or the low is below L, the setup is `INVALID`.
   3. If a touch holds (B5), record the touch bar and the active level.
   4. If there was a touch within the last 3 bars and the B6 conditions hold at t, emit `SIGNAL`: entry = close_t, stop = next level.
   5. Otherwise, if close_t is within 3% above the nearest buy-eligible level, label it `APPROACHING`.
4. After `SIGNAL`: if `close > entry*1.05`, label `EXTENDED`. For bars after t, a low below the stop means `STOPPED`.

**Tests to add:**
- An H confirmation that would require a future bar.
- A new high after confirmation (must reset).
- Touches at exactly level·(1+tol), and closes 0.01% below the level.
- Inclusive versus exclusive MA5 boundary values.
- Cross versus level volume tests.
- A gap-down stop fill.
- Prefix invariance: append random bars and assert that earlier states do not change.

---

## F. Sources

- chartschool.stockcharts.com: Fibonacci retracements; ZigZag; Dow Theory; candlestick bullish reversal patterns
- stockcharts.com/articles/mailbag/2009/05/using-the-fibonacci-retracements-tool.html
- thepatternsite.com/fib.html; /SwingSetup.html; /Hammer.html; /BullEngulfing.html; /pullbacks.html
- doi.org/10.1016/j.eswa.2021.115893 (Tsinaslanidis, Guijarro and Voukelatos)
- pmc.ncbi.nlm.nih.gov/articles/PMC8752186
- marketcalls.in (republished EWI Fibonacci tutorial); MoneyShow (Kennedy, Elliott rules)
- metatrader5.com fractals help; forums.babypips.com (swing-high definition)
- babypips.com/learn/forex/placing-stops-with-fibs
- download.kiwoom.com/hero4_help_doc/KiwoomHero4_AdvancedSearch.pdf; download.kiwoom.com/hero4_help_new/1337.htm
- tradingqna.com post by MarketSmith India (5% buy zone, 7–8%)
- tradingview.com scripts: Pocket Pivots, 7 Week Rule (secondary sources for Morales and Kacher)
- tilnote.io/pages/689b046edf13c4ef330e3e39 (summary of video rnO2FXqo3cs)
- ridibooks.com/books/4803000120 (돈의 시나리오)
- KOSPI data: blockmedia.co.kr/archives/260213 and /886879; mt.co.kr (2025-09-10, 2011-01-03, 2008-10-31); ajunews.com/view/20210706154430259; asiae.co.kr/en/article/2020032015331905393; brunch.co.kr/@35e8cb4b4cac47c/35; biz.newdaily.co.kr (2022-12-29); kbmaeil.com/article/20260729500608; bullstory.io (2026-06-19); stock.pstatic.net Hanwha report 20260729; local KIS cache.
- **Could not be fetched:** investopedia.com (blocked) and the full ScienceDirect text, so the zone width used in the Tsinaslanidis paper is unknown.


## trendline

# Topic C: Trendline breakouts (`trendline_break`). Source-backed parameters

Spec read: `G:/내 드라이브/Claude/Tech/docs/2026-10-14-chart-techniques-design.md` §3 (and §4, which reuses §3).
Working notes: `<scratch>/research/topicC_notes.md` (session scratch, not kept). Extracted source texts are in the same folder: `arxiv1302.txt`, `lmw.txt`, `kiwoom.txt`.

**About the phrases.** Copyright limits allow at most one short verbatim quote. The "supporting phrase" fields below are therefore close paraphrases. The numbers are exactly as the sources state them.

**Bulkowski numbers carry a caveat.** They come from US stocks priced above $5, in bull markets only, 1991–2021. Most of his trendline effects are tiny: about 2 points of average rise. Slope is the one exception, at about 10 points. Weight the score accordingly.

---

## 0. Summary table

| # | Parameter (spec item) | Proposed value | Main source(s) | Confidence |
|---|---|---|---|---|
| 1 | Swing-high pivot (minor high) | High[p] is the max of highs in [p−3, p+3]. Usable only from bar p+3 onward. | Bulkowski minorhl (±2 window); Bulkowski uptrendlines (his software waits 3 bars); Lo-Mamaysky-Wang lag d=3 | High for the confirmation lag; medium for k=3 |
| 2 | Price scale | Fit the line in ln(high), indexed by bar | Bulkowski trenddown/uptrendlines; StockCharts ChartSchool; neurotrader code | High |
| 3 | First anchor | Highest confirmed pivot high in the lookback. Alternative: the high of a heavy-volume bar (from the video). | Bulkowski 123tc / QTL (Sperandeo method); AAII disagrees | Medium |
| 4 | No-cut rule | Every bar from anchor A to t−1 has high ≤ line×1.005 and close ≤ line | Bulkowski QTL/QUTL; 김정환 (line must include intraday highs and lows); ChartSchool and AAII allow small violations | High for the rule; 0.5% is an implementation choice |
| 5 | Touch | A confirmed pivot high with line×0.985 ≤ high ≤ line×1.005 | Touch must be a minor high: Bulkowski QTL. 1.5% band: by analogy only (LMW's double-top tolerance). | High for the pivot requirement; low-medium for 1.5% |
| 6 | Touch count | 3 or more required, anchor included. Bonus at 5+. | Murphy Law #5; ChartSchool; Bulkowski QUTL; Bulkowski up-trendline trades; 2002 book (>4 touches) | High for ≥3; medium for 5+ |
| 7 | Touch spacing | Minimum 10 bars (implementation choice). "Wide" bonus when median spacing > 13 bars. | Bulkowski trenddown (median 13 days); uptrendlines (median 12 days) | Medium (small effect) |
| 8 | Length | Minimum is a config value (spec's 40 is acceptable). "Long" bonus at > 48 bars. | Bulkowski trenddown (median 48 days); uptrendlines (median 44 days) | Medium |
| 9 | Slope | ln-slope per bar. "Shallow" means \|b\| ≤ the median \|b\| of detected lines (median split, as Bulkowski did). | Bulkowski trenddown 56% vs 46%; uptrendlines; QUTL (~30° is "modest") | High that shallow is better; the threshold is an implementation choice |
| 10 | Volume trend before breakout | OLS slope of volume from A to t−1. Negative = bonus only, not a gate. | Bulkowski trenddown (52% vs 50%); glossary (regression from pattern start to end) | Medium for direction; the effect is tiny |
| 11 | Breakout bar | close[t] > line(t), every close from A to t−1 ≤ line, and close[t−1] ≤ line(t−1) | Bulkowski trenddown (first close above the line); Kiwoom crossover definition | High |
| 12 | Breakout volume | vol[t] ≥ 1.5 × mean(vol[t−50..t−1]), with bar t excluded from the average | O'Neil 40–50%; Edwards & Magee ("volume must rise"); Bulkowski evidence argues against a hard gate | Medium (sources disagree) |
| 13 | Confirmation (안착) | No close ≤ line since breakout, AND either (a) close ≥ line(t)×1.03, or (b) 3 consecutive closes above the line with the breakout bar as day 1 | Murphy 3% / two-day rule; Edwards & Magee ~3%; Penteado (citing Murphy 1986) 3% or 3 bars; the video's 3–4 days / 3–4% | Medium-high |
| 14 | Failure vs throwback | A pullback to the line is not a failure. Failure = a close below the frozen, extended line. Before confirmation that is a false breakout (가짜 돌파). | Bulkowski trenddown: throwback 59%, done in ~14 days | Medium |
| 15 | Target (display only) | Trendline start price (anchor A high), plus Bulkowski's measure rule (+56% of height) | Bulkowski trenddown: start reached 77% of the time | Medium |
| 16 | Bottom hammer | Lower shadow ≥ 2× body, small or no upper shadow, after a decline | ChartSchool; Kiwoom help (qualitative only) | High for the 2× ratio; "short upper shadow" number is an implementation choice |
| 17 | 9일 < 9주 < 9개월; 3 vs 8 touches; 3–4 days / 3–4% | No source found except the video | Only the qualitative "longer = more significant" is sourced (Murphy, Pring, ChartSchool) | Unverified |

---

## 1. Source digest (what each authoritative source actually says)

### 1.1 Bulkowski, down-sloping trendlines: https://thepatternsite.com/trenddown.html

**Sample and method**
- 3,274 lines from 645 stocks, Feb 1991 to Apr 2021, bull markets only, stocks above $5.
- Performance measure: the move from the breakout price to the ultimate high. The ultimate high is the peak before a decline of at least 20% (glossary).

**Breakout and drawing**
- Breakout = the first close above the trendline.
- Draw the line along price peaks, on a log scale. He says the log scale gives the trend-change signal sooner.

**Average rise after breakout, by feature**

| Feature | Split | Average rise |
|---|---|---|
| Touch spacing | median 13 days; wide vs narrow | 52% vs 50% |
| Length | median 48 days; long vs short | 52% vs 50% |
| Slope | median 0.05; shallow vs steep | 56% vs 46% |
| Inbound slope | −0.007..+0.05 vs outside | 56% vs 47% (the table says 46%; the page is inconsistent) |
| Volume trend | falling vs rising | 52% vs 50% |

- The spacing row is labelled "more touches / fewer touches" on the page, which looks like a typo for wide and narrow spacing.
- Slope is in price per day, not degrees. It is computed from closes as (TrendStart − LineStart) / (date difference).
- The inbound trend is the price move before the line starts. A flat inbound trend is the preferred case.

**Overall results**
- Average rise 51%, median rise 30%.
- Failure rates (share of breakouts that rise less than the threshold): 5%: 13%; 10%: 24%; 15%: 32%; 20%: 39%; 25%: 45%; 30%: 50%.
- Throwbacks happen 59% of the time. Price first rises about 5% over 9 days, and the throwback completes about 14 days after breakout. After a throwback completes, price rises 81% of the time.

**Targets**
- Measure rule: take the largest vertical distance between the line and price after the last touch, multiply by 56%, and add it to the breakout price.
- The trendline's starting price is reached 77% of the time.

### 1.2 Bulkowski, up-sloping trendlines: https://thepatternsite.com/uptrendlines.html

This is the mirror case. It is useful for the touch-count evidence and the confirmation lag.

**Sample**
- 3,720 lines (3,172 in bull markets), 699 stocks, Mar 1991 to Apr 2021.

**Trade test**
- Buy after the 3rd touch and sell after the first close below the line.
- Overall: average +0.7%, median −0.9%, 37% winners.

**Touch count**
- 3 touches: −2.1%.
- 4 touches: +2%.
- Gains rise up to 7 touches: +7.5%, but only 23 samples.

**Length, spacing and slope**
- Median length 44 days: long +2.9% vs short −1.4%.
- Median spacing 12 days: wide +2% vs narrow −1%.
- Median slope 0.05: shallow +2% vs steeper −0.7%.
- Best inbound slope is between −0.03 and +0.02.

**Confirmation lag (key implementation point)**
- He found the third touch, waited 3 price bars, then bought at the next open.
- His reason: his software needs 3 bars after a low to be sure it is a minor low.
- The only quote in this report is a fragment from this page: "3 bars after a minor low" (the rest is paraphrased above).

**Exit timing**
- Selling on the first close below the line beat waiting for a second close: median loss 0.9% vs 1.3%.

### 1.3 Bulkowski tutorials: https://www.thepatternsite.com/QTL.html and https://thepatternsite.com/QUTL.html

- Down-sloping lines go above the peaks.
- A touch only counts if it is a minor high.
- If the line cuts through price, that point does not count as a touch.
- A line with only two touches is weaker. Prefer the line with more touches.
- Longer lines, more touches, and wider spacing are all better. These pages give no numbers for them.
- Up-sloping lines need at least 3 touches. A modest slope of about 30° is more durable; steep lines end quickly.
- Scale and aspect ratio change the apparent angle, so degrees cannot be used directly.

### 1.4 Bulkowski, minor high/low and 1-2-3 trend change

- Minor high (https://thepatternsite.com/minorhl.html): no higher price within the 5-day window around the peak, i.e. 2 bars on each side. Peaks should be distinct and well separated.
- 1-2-3 method (https://thepatternsite.com/123tc.html), credited to Victor Sperandeo:
  - Draw from the highest high so the line does not cross price until after the lowest low.
  - Step 1: close above the line. Step 2: retest of the low. Step 3: close above the intervening high.
  - Down case: 73% (74 of 101) rose at least 20% from the low.

### 1.5 Bulkowski on volume

**Definitions**
- Glossary (https://www.thepatternsite.com/glossary.html):
  - Breakout volume is compared with the average of the prior 3 months.
  - Volume trend is a linear regression from the pattern's start to its end.
  - A throwback is a return to the breakout price within 30 days.
- https://thepatternsite.com/volbkout.html: heavy breakout volume means above the 30-day average.

**Newer study** (https://www.thepatternsite.com/VolumeStudy.html)
- Baseline: the 31 calendar days before the breakout.
- Sample: about 8,000 rectangles and double/triple tops and bottoms. **It does not cover trendlines.**

| Measure | Heavy breakout volume | Light breakout volume |
|---|---|---|
| Average rise, upward breakouts | 37.6% | 35.8% |
| Throwbacks | 57% | 18% |
| Failures | more | fewer |

**Older study** (https://www.thepatternsite.com/Volume.html)
- Its addendum says the gain from heavy volume is meager, while throwbacks and failures rise substantially.

### 1.6 Breakout-confirmation filters (Murphy, Edwards & Magee)

**Murphy, via Penteado (arXiv 1302.1228, https://arxiv.org/pdf/1302.1228)**
- Footnote 38 cites Murphy (1986), pp. 66–67 and 74, plus Edwards & Magee and Pring.
- Trend reversal rule:
  - The close must be at least 3% beyond the line.
  - Or the 3% can accumulate over the next 2 days.
  - Or the break counts if 3 bars move away after the cross, even with less than 3%.
  - This applies to both horizontal lines and trendlines.
- The paper also requires the two anchor highs to be at least 3 bars apart.

**Murphy-style filters, secondary sources** (I could not access the book itself)
- TigerShark / Andy Swan 2007 (http://www.tigersharktrading.com/articles/8406/1/When-Is-a-Trendline-Break-Valid/Page1.html):
  - 3% price filter on a closing basis, used mainly for long-term lines.
  - 1% for short-term trading.
  - Two-day rule: two successive closes beyond the line.
  - A close beyond the line matters more than an intraday pierce.
- Babypips threads say the same.

**Edwards & Magee, via Peter Brandt** (https://www.peterlbrandt.com/?p=12076)
- A decisive break closes beyond the line by about 3% of the price.
- Volume should rise notably on a genuine upside breakout.
- Brandt suggests 1–2% for commodities and FX.

**Edwards & Magee, via stockdisciplines** (https://stockdisciplines.com/stock-trends-penetrations/)
- 3% on the close (mental stop) or 6% on the intraday low (broker stop).
- Some traders require two consecutive closes.

### 1.7 General significance rules

- Murphy's 10 Laws, Law #5 (https://chartschool.stockcharts.com/table-of-contents/overview/john-murphys-10-laws-of-technical-trading): a valid line is touched at least 3 times. The longer it lasts and the more it is tested, the more important it is.
- StockCharts ChartSchool, Trend Lines (https://chartschool.stockcharts.com/table-of-contents/chart-analysis/trend-lines):
  - Two points draw a line; the third confirms it.
  - Steeper lines are less valid.
  - Spacing should be fairly even.
  - Spikes can be ignored "to a reasonable degree".
  - Semi-log scale lines up highs and lows better.
  - A break is a warning, not the final word.
- Pring (https://www.pring.com/glossary/trendline/): significance depends on length, the number of touches or approaches, and steepness. No numbers are given.
- AAII / Weiss 2017 (https://www.aaii.com/journal/article/rules-for-drawing-and-analyzing-trendlines):
  - Anchor at a secondary peak, not the major extreme, to reduce whipsaws.
  - Minor temporary violations happen.

### 1.8 O'Neil breakout volume

- LuxAlgo's O'Neil base-analysis page (https://www.luxalgo.com/library/concept/oneil-base-analysis.md): about 40% or more above average volume on the breakout. No averaging window is given.
- MarketSmith India (blog.marketsmithindia.com/gauge-demand-stock/, seen only in a search snippet; the domain did not resolve on fetch): at least 40–50% above average.
- DSIJ (search snippet): 50% above the 50-session average.
- All of these are for base breakouts, not trendlines.

### 1.9 Algorithmic and no-look-ahead references

**Lo, Mamaysky & Wang (2000)** (https://www.nber.org/system/files/working_papers/w7613/w7613.pdf)
- Rolling window l=35 plus a lag d=3. The lag is the number of days that must pass after a pattern completes before it is detected. They state this keeps conditional returns out-of-sample, without look-ahead.
- Raw 1-bar local maxima find too many extrema.
- Double-top highs must be within 1.5% of their average and at least 22 trading days apart (following Edwards & Magee).

**Pivot confirmation in Pine**
- `ta.pivothigh(left, right)` returns na until the right-side bars have closed, so a pivot appears only `right` bars late (https://pineify.app/pine-script/reference/ta/pivothigh).
- LuxAlgo "Trendlines with Breaks" (https://www.luxalgo.com/library/indicator/trendlines-with-breaks/): its lines can repaint as new pivots form, and it backpaints by `length` by default. This is exactly the trap to avoid.

**neurotrader TrendLineAutomation** (https://raw.githubusercontent.com/neurotrader888/TrendLineAutomation/main/trendline_automation.py)
- Works on log prices to remove scale effects.
- Resistance must sit above all highs, with tolerance 1e-5, and passes through the pivot.
- Fits over a rolling window that ends at bar i (example lookback 30).

**trendln** (https://github.com/GregoryMorse/trendln)
- errpct default 0.005 (0.5% slope standard error).
- Search window default 125.

### 1.10 Korean sources

**김정환《차트의 기술》, Kyobo e-book sample** (https://ebook-product.kyobobook.co.kr/dig/epd/sam/E000003218169)
- A trendline must not connect closes only; it must include each day's intraday highs and lows.
- When an intraday pierce happens, draw both the old line and the possible new line, then let later price action decide.
- The author says a standard for judging a real break is needed. **The sample cuts off before that standard.**
- None of the video's numbers appear in any accessible text: 9일 < 9주 < 9개월, 3 vs 8 touches, 3–4 days / 3–4%.

**Kiwoom condition-search help** (https://download.kiwoom.com/hero4_help_doc/KiwoomHero4_AdvancedSearch.pdf)
- p.3: upward cross = A below B on the prior bar and A above B on the current bar.
- Hammer description (around p.34): almost no upper shadow and a very long lower shadow. Only qualitative.
- **There is no trendline condition at all.**

**Korean community rules**
- 3:3 법칙 (https://steemit.com/kr/@lazyrodi/5): if price returns within 3 days or 3%, the old box is still valid. This is for boxes, not trendlines.
- Elex blog, 2012 (https://blog.elex.pe.kr/entry/%EC%B6%94%EC%84%B8%EB%B6%84%EC%84%9D), in a KOFIA-textbook style: confirm with the close, with a fixed amount or ratio, and with at least 2 consecutive days beyond the line.

### 1.11 Hammer

- StockCharts ChartSchool (https://chartschool.stockcharts.com/table-of-contents/chart-analysis/candlestick-charts/candlestick-bullish-reversal-patterns):
  - Lower shadow at least twice the body.
  - Small or no upper shadow.
  - Appears after a decline.
  - Needs further strength as confirmation.
- I did not verify Nison's own text.

---

## 2. Parameter-by-parameter recommendation (daily EOD, no look-ahead)

### P1. Pivot high
- **Definition:** H[p] ≥ max(H[p−3..p−1]) and H[p] > max(H[p+1..p+3]). A strict right side breaks ties toward the left bar.
- **Availability:** usable at bar p+3 or later. When deciding at bar t, use only pivots with p ≤ t−1−3, so the line is defined from data ≤ t−1 before bar t's close is tested.
- **Sources:**
  - Bulkowski minorhl uses a ±2 window.
  - Bulkowski's own software waits 3 bars (uptrendlines).
  - LMW use d=3.
  - Pine pivothigh only fires after the right-side bars.
- **Disagreement:** k=2 (Bulkowski's definition) vs k=3 (his software and LMW). The spec's k=3 is supported.
- **Config:** k ∈ {2, 3}, default 3.

### P2. Scale
- Work in y = ln(High). Line: ℓ(i) = a + b·i, where i is the trading-bar index.
- Sources: Bulkowski recommends log scale on both trendline pages; ChartSchool says semi-log lines up better; neurotrader takes the log to fix scaling.
- **Bars vs days:** Bulkowski's "days" match his "price bars" in the uptrendlines text, so bar counts are fine.

### P3. Anchor A (first point)
- **Default:** the highest confirmed pivot high in the lookback window.
- **Alternative (video [21:00]):** pivot highs whose bar volume is at least 2× the 50-day average. The 2× is an implementation choice.
- **Sources:**
  - Sperandeo 1-2-3, via Bulkowski 123tc and QTL: draw from the highest peak.
- **Disagreement:** AAII/Weiss says to start from a secondary peak, not the major extreme, to avoid whipsaw. Optionally keep it as a third candidate.

### P4. Lookback
- 250 bars (about 1 year). **No source found; implementation choice.**
- Rationale: it covers the video's 9-month tier (~189 bars) and is well above Bulkowski's median length of 44–48 days. trendln defaults to 125 bars for reference.

### P5. No-cut (캔들 관통 금지)
- For all i in [A, t−1]:
  - H[i] ≤ ℓ(i) + ln(1.005)
  - Close[i] ≤ ℓ(i)
- Why the close condition:
  - Bulkowski defines the breakout as the *first* close above the line.
  - Any earlier close above the line means the breakout already happened, so the setup is stale.
- **Sources:**
  - Bulkowski QTL/QUTL: a line that cuts price is not counted.
  - Sperandeo: no crossing until after the low.
  - 김정환: the line must contain intraday highs.
- **Lenient side:** ChartSchool lets spikes be ignored to a reasonable degree; AAII allows minor temporary violations.
- **Strict side:** neurotrader uses zero tolerance.
- **The 0.5% is an implementation choice** between those two positions.

### P6. Touch
- A confirmed pivot high p in [A, t−1−k] with ℓ(p) − ln(1.015) ≤ ln H[p] ≤ ℓ(p) + ln(1.005).
- Only pivots count. Bulkowski QTL: point 3 is not a minor high, so it is not a touch.
- **The 1.5% band has no trendline-specific source.**
  - Closest analog: LMW's 1.5% tolerance for two tops being "equal".
  - Possible alternative: a band of 0.5×ATR14/close. Also unsourced.

### P7. Touch count
- **Requirement:** at least 3 touches including A. Sources: Murphy Law #5, ChartSchool, Bulkowski QUTL.
- **Bonus:** 5 or more touches.
- **Evidence for the bonus:**
  - Bulkowski up-trendlines: 3 touches lost 2.1%, 4 touches gained 2%, rising to +7.5% at 7 touches (only 23 samples).
  - *Unverified secondary:* Bulkowski, *Trading Classic Chart Patterns* (Wiley 2002), trendline chapter, as seen only in a web-search snippet of a third-party copy. More than 4 touches gave 48% average rise (n=62) vs 35% for 4 or fewer (n=148). Check the book before citing.
- The video's "8 touches" was not found in any source.

### P8. Spacing
- **Minimum gap:** 10 bars between consecutive touches. **Implementation choice (no source).**
  - The only sourced minimum is Penteado's "at least 3 bars apart", which k=3 pivots already guarantee.
- **"Wide" bonus:** median gap above 13 bars (Bulkowski down-trendline median; 12 for up-trendlines).
- The 2002 book (unverified) used a 29-day midrange: 41% vs 36%.
- The effect is small: 52% vs 50%.

### P9. Length
- L = t_breakout − A, in bars.
- **"Long" bonus:** L > 48 (Bulkowski down-trendline median: 52% vs 50%). For up-trendlines, lines longer than 44 bars were profitable and shorter ones lost money.
- **Minimum:** a config value. **No source.** The spec's 40 sits just under Bulkowski's median, which means it drops roughly half of his sample. Consider 20–30 as the minimum and use the 48-bar grade instead.
- **Video tiers** (9일 / 9주 / 9개월 ≈ 9 / 45 / 189 bars) are **unverified**. Only "longer = more significant" is sourced.
  - Note: 9 weeks ≈ 45 bars, which happens to match Bulkowski's 44–48 bar median.

### P10. Slope
- **Measure:** b in ln units per bar (b < 0). Also show it as %/bar = (e^b − 1).
- **Grade:** "shallow" if |b| ≤ the median |b| across all lines detected in the universe over a calibration period. This copies Bulkowski's median-split method, not his number.
- **Why not Bulkowski's 0.05:** it is in dollars per day for US stocks, so it does not transfer to KRW prices.
- **Weight:** slope gets the largest weight among the four Bulkowski principles: 56% vs 46%, against about 2 points for spacing, length and volume trend.
- 30° (QUTL) and Murphy's angle guidance depend on chart scale, so they cannot be implemented.

### P11. Inbound trend (optional bonus)
- **Measure:** OLS slope of ln(Close) over the 20 bars before A. The 20-bar window is an implementation choice.
- **Bonus:** if the slope is near flat.
- **Source:** Bulkowski down-trendlines: flat inbound slope gave 56% vs 47%.
- His numeric range is in dollars per day, so the threshold is an implementation choice.

### P12. Volume trend before breakout
- **Measure:** OLS slope of Volume over [A, t−1]. Negative = "falling", bonus only.
- **Source:** Bulkowski glossary (regression over the pattern) and trenddown (52% vs 50%).
- **Do not make it a gate.** The effect is about 2 points.

### P13. Breakout bar t0
- **All of the following must hold:**
  - Close[t0] > exp(ℓ(t0))
  - Close[t0−1] ≤ exp(ℓ(t0−1))
  - The P5 conditions hold on [A, t0−1]
- **Sources:** Bulkowski's first close above the line; Kiwoom's crossover definition.
- An intraday high above the line without a close above it is **not** a breakout (Murphy/TigerShark: closes matter; 김정환: intraday pierces are hard to judge).

### P14. Breakout volume
- **Gate:** V[t0] ≥ 1.5 × mean(V[t0−50..t0−1]), with the breakout day excluded from the average.
- **The exclusion follows Bulkowski:** his average runs up to but not including the breakout day (volbkout and glossary describe the baseline that way).
- **For the gate:**
  - O'Neil (40–50% above average): 1.4–1.5×.
  - Edwards & Magee: volume should rise notably on an upside break.
  - The video calls it mandatory.
- **Against a hard gate:** Bulkowski's own data show only +1.8 points of gain with heavy volume, about 3× more throwbacks (57% vs 18%), and more failures. That study covered rectangles and doubles, not trendlines.
- **Recommendation:** keep the 1.5× gate per the spec, and record the ratio. Optionally emit a separate stage, "돌파(거래량 미달)", rather than dropping the candidate silently.

### P15. Confirmation (안착 확인)
Let t0 be the breakout bar, counted as day 1. For t ≥ t0, while every close since t0 has stayed above its line value:
- **(a) Price filter:** Close[t] ≥ 1.03 × line(t). Murphy's 3% filter, Edwards & Magee's ~3% of price, and Penteado all measure **against the line**.
- **(b) Time filter:** closes above the line on bars t0, t0+1 and t0+2, i.e. 3 consecutive closes.
  - Penteado: 3 bars after the cross.
  - The video says 3–4 days.
  - Murphy's two-day rule is the lenient variant; make N ∈ {2, 3} a config value, default 3.

**Differences from the spec:**
- **Measure the 3% from the line, not from the breakout-day close** ("돌파일 종가 대비 +3%"). If the breakout close is already 2% over the line, the spec's version demands about 5% above the line, which is stricter than any source.
- **Penteado's cumulative variant:** 3% reached by day 3 is already covered by (a) evaluated on each bar.
- **3% is for long lines:** Murphy/TigerShark use 3% for long-term lines and 1% for short-term. The spec's minimum length of 40+ bars fits 3%.

### P16. Failure vs throwback
- **Before confirmation:** a close ≤ line(t) means a false breakout (실패, 가짜 돌파).
- **After confirmation:**
  - A return toward the line is normal: throwbacks happen 59% of the time and complete in about 14 days. Do **not** flag failure on a touch.
  - Failure = Close < line(t) on the **frozen** line extended forward. This mirrors Bulkowski's first-close-below exit, which beat waiting for a second close (0.9% vs 1.3% median loss).
  - Optionally require a 3% filter below the line. Implementation choice.
- Reference base rate: 13% of down-trendline breakouts fail to rise 5% (Bulkowski).

### P17. Targets (display only, not a signal)
- **T1 = high of anchor A** (the trendline start). Bulkowski: reached 77% of the time.
- **T2 = breakout price + 0.56 × D.** D is the largest vertical gap between the line and the lowest low after the last touch before breakout (Bulkowski measure rule).

### P18. Bottom hammer (spec §3 observation flag)
- Lower shadow ≥ 2 × |body| (ChartSchool).
- Upper shadow ≤ 0.1 × (High − Low). **Implementation choice:** ChartSchool and Kiwoom only say "small or nonexistent".
- Inside 20 bars before t0 and within a decline. The 20 bars is an implementation choice.

### P19. 돌파 임박 (within 2% below the line)
- **No source found.** Implementation choice. A reasonable rationale: it matches the touch band order of magnitude (1.5%).

---

## 3. Where sources disagree (keep these as configuration flags)

1. **Pivot window:** ±2 bars (Bulkowski definition) vs a 3-bar confirmation (Bulkowski software, LMW).
2. **Anchor:** highest peak (Sperandeo/Bulkowski) vs heavy-volume candle (the video) vs secondary peak (AAII).
3. **Violation tolerance:**
   - Strict: Bulkowski, neurotrader, 김정환's intraday-high rule.
   - Lenient: ChartSchool ignores spikes "to a reasonable degree"; AAII allows minor violations.
4. **Confirmation:** 3% (Murphy, Edwards & Magee) vs 1–2% (TigerShark short-term, Brandt) vs 2 closes (Murphy, KOFIA-style) vs 3 bars (Penteado, video 3–4).
   - Edwards & Magee also allow 6% on the intraday low when a broker stop is used.
5. **Breakout volume:** required (Edwards & Magee, O'Neil, the video) vs weak or counterproductive (Bulkowski: more throwbacks and failures).
6. **Touch count vs post-breakout move:** in Bulkowski's up-trendline data, trading after the touch favors more touches, but the decline after the breakout was slightly *larger* for 3-touch lines (13.4% vs 13.0–13.1%). Touch count is not a clean monotonic edge.
7. **Spacing medians:** 12 vs 13 days on the website vs 29 days in the 2002 book (unverified). Different samples.

---

## 4. EOD algorithm without look-ahead (sketch)

```
params: k=3, L_lookback=250, tol_cut=0.005, tol_touch=0.015, min_gap=10,
        min_touches=3, min_len=40 (config), vol_mult=1.5, vol_win=50,
        conf_pct=0.03, conf_bars=3

state per symbol: frozen_line = None

on each completed bar t:
  if frozen_line is None:
    P = [p for p in pivots_high(k) if p + k <= t-1 and p >= t-L_lookback]   # confirmed by t-1
    cands = []
    for A in anchor_candidates(P):          # highest pivot; optional heavy-volume pivots
      # tightest non-cutting line from A over (A, t-1]: b* = max_i (lnH[i] - ln(1+tol_cut) - lnH[A])/(i-A)
      b = max((lnH[i] - log1p(tol_cut) - lnH[A])/(i-A) for i in (A+1 .. t-1))
      if b >= 0: continue                      # must be descending
      line(i) = lnH[A] + b*(i-A)
      if any(Close[i] > exp(line(i)) for i in A..t-1): continue   # an earlier close above = stale
      touches = [p in P, p>=A, line(p)-ln(1+tol_touch) <= lnH[p] <= line(p)+ln(1+tol_cut)]
      enforce gaps >= min_gap; require len(touches) >= min_touches and (t - A) >= min_len
      cands.append((len(touches), t-A, -abs(b), A, b))
    best = max(cands) by (touches, length, shallowness)   # Bulkowski QTL prefers more touches
    if best and Close[t] > exp(line_best(t)) and Close[t-1] <= exp(line_best(t-1)):
      vr = V[t] / mean(V[t-vol_win .. t-1])                # breakout bar excluded
      emit BREAKOUT(t0=t, line=best, vol_ratio=vr, gate=vr>=vol_mult, scores...)
      frozen_line = best                                   # never refit after this point
    elif best and Close[t] >= 0.98*exp(line_best(t)): emit NEAR (돌파 임박)
  else:
    # stage machine on the frozen line only
    if Close[t] <= exp(line(t)): FAIL (false break if not yet confirmed, else failure)
    elif Close[t] >= (1+conf_pct)*exp(line(t)) or bars_since_t0+1 >= conf_bars: CONFIRMED
    else: CONFIRMING
```

**Notes**
- **Why b\* is computed this way:** it is the slope of the upper hull from A, i.e. the "swing the line until it touches" step in Sperandeo's construction. It costs O(n) per anchor.
- **Only fully closed bars are used.** No future pivot can change a decision already emitted, because:
  - Pivots must satisfy p + k ≤ t−1.
  - The line is frozen at t0.
  - Volume averages exclude the current bar.
- **Repainting:** LuxAlgo warns that its lines repaint because they are refit as pivots form. Store the detection-time line (A, b, touches) in the signal record and draw that exact line on the report chart.

---

## 5. Tests implied by the sources (add to the spec §테스트)

- **Prefix invariance:** for every t, signal(data[:t+1]) == signal(data[:T]) for all T > t. Include a case where a new, higher pivot appears after t0.
- **Pivot lag:** a peak at p with only 2 lower bars to its right must not count as a touch until bar p+3.
- **Earlier close above the line:** a close above the line before t0 invalidates the candidate.
- **Intraday pierce:** a high above the line with the close below it is not a breakout.
- **Two touches:** rejected. Three touches accepted. Five touches get the bonus.
- **Confirmation measurement:** breakout close 2% above the line, next close 3.1% above the line(t) → CONFIRMED on day 2 under (a). Under the spec's "breakout close +3%" this would not confirm. This is the regression case for the recommended change.
- **Throwback:** after confirmation, price drops to within 0.5% above the line → still CONFIRMED. A close below the line → FAIL.
- **Volume baseline:** the breakout day must be excluded from the 50-day average. The case: 49 normal days plus a huge breakout day.

---

## 6. Not found or unverified (do not present as sourced)

- 김정환's 9일 < 9주 < 9개월 hierarchy, "3 vs 8 touches", and "3–4 days or 3–4%":
  - Searched Korean book listings, the Kyobo sample, blogs and news.
  - The sample stops right before the author's criterion. Treat these as **video-only claims**.
- Murphy's exact wording on the 3% filter and the 2-day rule: confirmed only through secondary sources.
  - Penteado cites Murphy 1986 pp. 66–67 and 74. TigerShark and Babypips paraphrase it.
  - The book text was not accessible: no legal online copy; traders.com and O'Reilly blocked access.
- The 2002 *Trading Classic Chart Patterns* trendline table: seen only in a search-engine snippet of a third-party copy that I did not open. Verify in the book.
- Bulkowski's 2002 S&C article "The Truth About Trendlines": blocked by Cloudflare. Not used.
- A trendline-specific touch tolerance (the 1.5%) and a minimum touch spacing (10 bars): no source; implementation choices with the rationale given above.


## exit_ma

# Topic D: exits, moving averages, Bulkowski checklist, +10% day leader

Notes were saved at `<scratch>/research/topicD_notes.md` (session scratch, not kept).

**How sources are cited.** Copyright policy lets me reproduce at most one short verbatim quote. So "supporting phrase" below is a close paraphrase plus the page or section where it appears. Numbers are copied exactly. The single verbatim quote is in D3-9.

**Confidence scale.** H = primary source, or the author's own site. M = a secondary source that faithfully summarises the author, or two sources that agree. L = blog or community posts only.

---

## 0. Findings that change the spec (read first)

1. **The 10-day sell rule only applies to some stocks.** The 2-step violation definition in the spec matches Morales/Kacher. But in their method the 10-day line is the sell guide only after a stock has held above it for 7 weeks (35 bars) from the buy point. Otherwise the 50-day line is the guide.
2. **Bulkowski tested this rule and was disappointed.** He backtested the Kacher–Morales rules on 557 stocks. Waiting for the lower low made results worse than selling the day after the close below the average.
3. **Checklist 9 (dead-cat bounce) can be detected from prices alone.** Bulkowski's event is a one-day close at least 15% below the prior close. His checklist says to avoid the stock for 6 months. The spec currently leans on disclosure JSON. Add the price rule and keep disclosures as an extra tag.
4. **Checklist 7 contradicts Bulkowski as written.** His checklist favours patterns near the yearly high, ideally a new high. "Within 10% of the 52-week high = warning" has no source and inverts his item. Redefine it as the nearest overhead resistance (D3-7). His own statistics (buylow.html) actually favour the yearly low, so his sources also disagree with each other.
5. **Checklist 10 (consecutive up days) has no number in Bulkowski.** His breakout study found that more than 3 consecutive higher closes into a breakout gives better performance and fewer throwbacks. So this item should be a soft caution, not "추격 금지".
6. **Checklist 5 (industry RS) has a defined method.** Bulkowski ranks industries by the average 6-month % change of member stocks. His top group is ranks 1–11 of 44, about the top quarter, not the top third.
7. **Checklist 8 (stop) gets a sourced number.** Bulkowski's volatility stop is 2 × the average daily (high − low) over 22 bars, subtracted from the current low. A stop should be no closer than that.
8. **60일선 수급 confirmation has no number anywhere.** No source gives a count of net-buying days, including the video summary. It stays an implementation choice.
9. **The basis for "+10%" is unverified.** The only text summary of the video says "당일 10% 이상 상승" without saying whether that is vs the open or vs the prior close. The spec's "시가 대비" cannot be confirmed. The KRX static VI (±10% from the last single price) is a structural reason "시가 대비 10%" matters intraday.

---

## D1. Exits: Morales/Kacher 10- and 50-day rules, the 20-day line, the Korean 5-day line

| Parameter | Proposed value | Source(s) | Supporting paraphrase | Conf. |
|---|---|---|---|---|
| MA type for the 10- and 50-day lines | Simple MA on close | thepatternsite.com/KacherMorales.html; tradingview.com/script/kDC1dFjU-7-Week-Rule/ | Bulkowski defines "violates" against the simple MA. The TradingView 7-Week Rule script defaults to 10SMA. The book excerpts don't name the type. | M |
| Step 1: arm | First close below the MA | everand.com/book/343295426 (*In the Trading Cockpit with the O'Neil Disciples*, Fig. I.6 discussion) | The authors say the first close below an MA is not itself a violation. | H (book preview) |
| Step 2: trigger | Price trades below the intraday low of the arming day | Same Everand page; TradingView 7-Week Rule; Bookmate quotes of *Trade Like an O'Neil Disciple* (via search snippet; page returned 403); edgerater.com/blog/morales-and-kacher-signals-template | A violation needs a later move below the intraday low of the first day that closed under the 10-day line. | H |
| Trigger timing window | Default: the next bar only. Config: `VIOLATION_WINDOW = 1 \| until_reclaim` | **Sources disagree.** Next day: TradingView script and the Bookmate quote of the 2010 book. No timing stated: the Everand *Cockpit* excerpt and Edgerater ("subsequently"). Bulkowski reads it as "following day(s)". | The Cockpit example treats a stock that recovered over two days without undercutting the low as a non-violation. | M |
| Numeric porosity around the MA | None. The 2-step rule is the porosity mechanism. | edgerater (porosity allowed, no number); whatheheckaboom.wordpress.com 2014-08-16 review | Neither gives a % for MAs. Buyable gap-up stop porosity differs by source: 1–2% below the gap-day low (review) vs about 2–3% (Everand excerpt). This is not an MA rule; it matters for other topics. | M |
| 7-week rule | Window = 35 trading days after entry. If there is no 10-day violation in that window, the 10-day line is the sell guide. If there is, switch to the 50-day line. | Everand Cockpit excerpt; townhall.com/author/print/903240 (Morales & Kacher, "Short the Market", 2011-10-15); edgerater (~35 trading days); TradingView (35 days closed above) | The column applies the 50-day switch when the position is profitable. For losing positions, the 2014 review says to judge by stock quality and market strength. | H/M |
| 50-day violation | Same 2-step test on SMA50 | in.tradingview.com/chart/VNINDEX/AgmKyPf9 (secondary); Bulkowski KacherMorales.html | A breach is a break of the 50-day, then trading below the breach-day low the next day. | M |
| Bulkowski's extra exceptions (not found in Morales' own text) | Optional: use the 50-day line for semiconductors, retail, commodities, or market cap > $5B | KacherMorales.html | Treat as Bulkowski's reading. Converting $5B to KRW is your call. | L–M |
| Effectiveness caveat | Show the rule; don't claim an edge | KacherMorales.html (557 stocks, 2001-03-12 to 2010-10-01) | The lower-low wait made results worse than selling the day after the close below the MA. Bulkowski says he was disappointed. | H (his test) |
| 20-day line | No Morales/Kacher 20-day rule found. In Korean usage the 20일선 is the 단기생명선. | mt.co.kr 2008-10-15 "[오늘의포인트]10일 이평선 활용 투자전략" | The 20-day line is called the short-term life line where short and long trends meet. The IBD 21-day EMA is a Market School (index) tool; I could not confirm it as a stock sell rule (investors.com blocks fetches). | M (naming) |
| O'Neil "50-day break on heavy volume" | Do not use as a sourced rule | Only low-quality summaries found | Unverified. | — |
| Korean 1st exit (5-day line) | `close[t] < SMA5[t]` (close basis) | tilnote.io/pages/689b046edf13c4ef330e3e39 (summary of the video rnO2FXqo3cs); m.cafe.daum.net/Antsstory/DJzh/152 (2011-11-29); sisaon.co.kr idxno=2026 (2010-04-06, 전석) | The video summary sets take-profit at a 5-day or 10-day line break. The cafe post buys on a close above the 5-day line and sells on a close below it. The Sisaon column treats "anchored" as ≥3/4 of the body above the line, buys at the next open, and sells on the mirror condition. "종가 기준" comes from the community sources; the video summary doesn't say. | L–M |
| Bulkowski's own sell signals (useful cross-checks) | Close below an up-sloping trendline = first warning. Retrace > 62% = sell. | thepatternsite.com/tradehelp.html, "When to Sell?" | This corroborates the fib-pullback rule "invalid below 61.8%". | H |

**Coding on daily EOD bars, no look-ahead** (all MAs use bars ≤ t):
```
sma10, sma50, sma5 = SMA(close, n)

# Arm and strict trigger (VIOLATION_WINDOW = 1)
arm10[t]  = close[t] < sma10[t] and close[t-1] >= sma10[t-1]
viol10[t] = arm10[t-1] and low[t] < low[t-1]     # known at close of t

# until_reclaim variant
ref = low[first close below]
violation = first later bar k with low[k] < ref and no close > sma10 in between

# Backtest fill (intraday event on the violation day)
fill = min(open[k], ref - 1 tick)

# Display for today, when close[t] < sma10[t]
"내일 {low[t]} 하회 시 10일선 위반"

# 7-week rule, with entry bar e
guide = 10 if not any(viol10[e+1 .. e+35]) else 50   # decided at bar e+35, or at the first violation

# 5-day line exit
exit5[t] = close[t] < sma5[t]
fill = close[t]        # or open[t+1] to be conservative
```
For the spec's display-only "청산 계획", use the signal bar as the hypothetical entry. Show both lines (10일 위반가 = today's low if close < SMA10; 50일선 value) and the 7-week caveat.

---

## D2. 60일선 수급선, 120일선 경기선, net-buying confirmation

| Parameter | Proposed | Source(s) | Paraphrase | Conf. |
|---|---|---|---|---|
| 60일선 = 수급선 | SMA60 on close | sgsg.hankyung.com/article/2005102520411 (한국경제 생글생글, 2005-10-31) | The medium-term 60-day line is driven by supply and demand (buying vs selling), hence the name. The same article calls the 5- and 20-day lines 재료선. | H (naming convention) |
| 120일선 = 경기선 | SMA120 | mt.co.kr 2003-04-29 "[내일의전략] 경기선 = 630"; mt.co.kr 2008-04-20 "120일 이동평균선 돌파가 관건" | Both name the 120-day MA the 경기선. **Disagreement:** 한국경제 2005 says the 120- or 200-day line. Keep 120 for KRX, the common HTS default. | H |
| 60일선 breakout | `close[t-1] <= sma60[t-1] and close[t] > sma60[t]` | Spec, and the tilnote summary of the video | The video says a short-term golden cross near a bottom is often only a bounce. A real trend change needs the 60일선 break plus institutional and foreign buying. | M (video only) |
| 수급 confirmation: number of days | **No source found. Implementation choice.** `수급 동반` if the (기관+외국인) net buy on day t > 0 and the 5-day sum (t−4..t) > 0. `쌍끌이` if 기관 and 외국인 are each > 0 over 5 days. `수급 역행` if the 5-day sum < 0. `수급 미확인` if there is no data. | tilnote states no number. Searches of Korean news, wikidocs and Kiwoom help found no standard count. | Rationale: 5 days = one trading week, which matches the spec. Kiwoom 0150 lets users stack one condition per day (N days back), so N is user-chosen. I saw that only in a search summary; wikidocs returned 403. | — |
| Data | Value (원) net buying is better than shares. Use only rows dated ≤ t. KRX investor data is published after the close. | — | Implementation note. | — |

---

## D3. Bulkowski checklist (primary: thepatternsite.com/tradehelp.html, "Bulkowski's Trading Checklist")

| Spec # | What Bulkowski says (paraphrase, exact numbers) | Proposed coding | Conf. |
|---|---|---|---|
| 1 Market trend | Trade in the direction of the prevailing market trend. No numbers. | Keep market.py | H (no number) |
| 2 Industry | Check whether industry peers are topping or bottoming, and which stock leads the group. | Keep sector.py | H |
| 3 Weekly | Look at the weekly (next higher) scale for threatening patterns, trend, support/resistance and trendlines. No MA given. | The spec's weekly close > 10-week MA is an implementation choice. 10 weeks ≈ 50 days (5 bars per week, arithmetic). Use **completed weeks only**. | H item / choice for the rule |
| 4 Historical review | Find another pattern in the same stock and see how it performed. | Matches the spec's replay idea. | H |
| 5 Industry RS | The industry must be "top ranked". Method (industryRS.html): each industry is ranked daily by the average % change of its stocks vs 6 months ago. 44 industries in groups 1–11 / 12–22 / 23–33 / 34–44. A group is held on average 21–47 days (top group in bull markets: 47 days). His trading test sold when rank fell below 14. | `rs_ind = mean(close[t]/close[t-126]-1 over members)`; pass if in the top quartile. ⅓ remains a defensible choice. | H |
| 6 Trending up | Wait for price to turn up before buying. No MA given. | The spec's close > 20/60-day lines is an implementation choice. | H item |
| 7 Resistance / yearly high | Checklist: buy patterns near the yearly high, preferably breaking to a new high, and look for overhead resistance. **Conflict:** buylow.html (bull market, upward breakouts) shows avg rise 38% in the lowest third of the yearly range (1,421 samples) vs 36% in the highest third (2,715). Fail-to-rise-10%: 12% vs 16%. He concludes to buy near the yearly low. | Replace "52주 고점 10% 이내 경고". Resistance = lowest confirmed swing high above entry within 252 bars. If close ≥ the prior 251-bar high, show "위 저항 없음(신고가)". Any % threshold is an implementation choice. | H (both pages) |
| 8 Support / stop | Stop "no closer than 2× current volatility". stops.html: average daily (high − low) over **22 bars × 2**, subtracted from the current low. The multiplier used to be 1.5. In his ~100 own trades (2003–05), the average give-back after the peak was 6.88%. | `vstop = low[t] - 2*mean(high-low, 22)`. Warn if the technique stop is above vstop (too tight). | H |
| 9 Dead-cat bounce | **The one verbatim quote:** "Avoid any stock showing a dead-cat bounce within the last six months." (tradehelp.html). Event (dcb.html): close 15%–70% below the prior close, usually on a gap down. The *Encyclopedia of Chart Patterns* 2nd ed. ch. 54, as reproduced by sacredtraders.com/dead-cat-bounce, says he used a 15% minimum and no bullish pattern within 6 months; the plunge usually lasts 1–2 days. **Disagreement:** a 1999 *S&C* article used 25%–70% (seen only as a search snippet; 403). His DCB *buy* setup uses 41–46%. The video summary says 6개월~1년. | `dcb_event[t] = close[t]/close[t-1]-1 <= -0.15` on adjusted prices; skip corporate-action days. `dcb_flag[t] = any(dcb_event[t-125..t])`, since 126 bars ≈ 6 months. Optional 12-month window as "참고". Before 2015-06-15 the KRX daily limit was ±15% (±30% since; etoday 2015-05-19), so a −15% day then was limit-down. Optional pre-2015 variant: 2-day close ≤ −15%. Bulkowski's definition needs no news, so disclosure JSON is only an extra tag. | H |
| 9 stats (context) | dcb.html: average decline 31%. 46% make a lower low the next day. Trend low in about 7 days. Bounce 28% over 23 days. Post-bounce decline 30% over 49 days. 67% end about 18% below the event low. 26% have a second DCB of ≥15% within 3 months; 38% have one within 6 months. Gap closes in 22% during the bounce, 38% within 3 months, 58% within 6 months. Swing-buy only if the event drop is over 30%. | Display only | H |
| 10 Consecutive up days | Checklist: after an upward run of several days, expect a reversal right after you buy. No count given. Also tighten stops if the stock shoots up over several days. **Conflict:** QConsecutive.html says more than 3 consecutive higher closes into an upward breakout gives better performance, fewer throwbacks, and about half as many failures. | `up_streak` = consecutive `close > close[-1]` ending at t. Soft caution "연속 상승 N일" if ≥4. The spec's "4 of 5 days and +20%" is an implementation choice. Don't block. | H items / choice |
| Extra | Skip the trade if the stock is up too much intraday (no %). Throwbacks turn about 3 days after a breakout and return to the breakout price in 10–11 days; the original direction resumes 86% of the time. | Show as informational notes | H |

---

## D4. The "+10% strong-day leader" (daily-observable part only)

| Parameter | Proposed | Source(s) | Paraphrase | Conf. |
|---|---|---|---|---|
| Trigger basis | Compute both: `up_open = C/O-1 >= 0.10` (spec) and `up_prev = C/C[-1]-1 >= 0.10`. Make one the main flag and show the other. | tilnote video summary | It targets stocks that rose 10%+ that day without saying vs what. The "시가 대비" basis is **unverified**. | L |
| Structural reason for 10% | Static VI triggers at ±10% from the last single price, followed by 2 minutes of single-price trading | download.kiwoom.com/kiwoom_easy_help_new/5110.htm; etoday 2015-05-19 | Reference = the single price just before the order. After the opening auction that is the open; this is my inference. Some sources (kbthink) say prior close, so this is disputed. | M |
| Volume | ≥ 3× the 20-day average volume, excluding day t. **No source. Implementation choice.** | A low-authority blog (thecheck.co.kr) cites 5–10× for "세력" bars. | Rationale: excluding t stops the spike inflating its own baseline. | — |
| Fib reference prices | Day-t low→high: `H - r*(H-L)`, r = .236 / .382 / .5 (.618 shown) | tilnote | The video's auto indicator ratios are 0.236, 0.382, 0.5, 0.618, 1, 1.618, drawn from the recognised low and high. Bar size (1/3/5-minute) is unspecified; the spec's "3분봉" is unverified. Entry is a support-bounce candle at 38.2%. The summary's stop wording reads oddly ("전고점 하방 이탈"). | L–M |
| Authoritative parallel (intraday, not codeable on EOD) | — | thepatternsite.com/Daytrade.html | Bulkowski looks for a straight-line run and expects a reversal at the 38% or 50% retrace. He enters when the stock and a 10-minute index chart turn the same way, waits more than one bar, and makes at most 2 consecutive swing trades. | H |
| Look-ahead | Levels are computed after day t closes and shown for day t+1 | — | A daily bar can't tell whether the low came before the high. Flag "저가→고가 순서 불명" when `(O-L)/(H-L) > 0.3` (implementation choice). | — |

---

## Where sources disagree
1. 10-day violation timing: next day only (TradingView script, 2010-book quote) vs any later day (*Cockpit* excerpt, Edgerater, Bulkowski).
2. Buyable gap-up porosity: 1–2% (2014 review) vs about 2–3% (Everand excerpt).
3. Dead-cat bounce minimum drop: 15% (site, *Encyclopedia* 2nd ed.) vs 25% (1999 article) vs 41–46% (his buy setup). Avoidance window: 6 months (Bulkowski) vs 6–12 months (video summary).
4. Yearly high vs low: the checklist prefers the high; buylow statistics prefer the low.
5. Consecutive up days: the checklist warns; his breakout study finds runs of more than 3 closes help.
6. 경기선: 120-day (머니투데이) vs 120- or 200-day (한국경제 2005).
7. Static VI reference: last single price (Kiwoom) vs prior close (kbthink).

## Sources
- https://www.everand.com/book/343295426/In-The-Trading-Cockpit-with-the-O-Neil-Disciples-Strategies-that-Made-Us-18-000-in-the-Stock-Market
- https://www.tradingview.com/script/kDC1dFjU-7-Week-Rule/
- https://edgerater.com/blog/morales-and-kacher-signals-template
- https://townhall.com/author/print/903240
- https://thepatternsite.com/KacherMorales.html
- https://whatheheckaboom.wordpress.com/2014/08/16/book-review-of-in-the-trading-cockpit-with-the-oneil-disciples-by-gil-morales-and-chris-kacher/
- https://in.tradingview.com/chart/VNINDEX/AgmKyPf9-Vnindex-Apr-2022-Rules-of-violation-of-the-50-day-MA
- https://thepatternsite.com/tradehelp.html
- https://www.thepatternsite.com/dcb.html
- https://thepatternsite.com/DCBSetup.html
- https://sacredtraders.com/dead-cat-bounce/
- https://www.luxalgo.com/library/concept/dead-cat-bounce.md
- https://www.thepatternsite.com/QConsecutive.html
- https://thepatternsite.com/buylow.html
- https://thepatternsite.com/industryRS.html
- https://thepatternsite.com/stops.html
- https://thepatternsite.com/Daytrade.html
- https://sgsg.hankyung.com/article/2005102520411
- https://www.mt.co.kr/stock/2003/04/29/2003042918362686531
- https://www.mt.co.kr/stock/2008/04/20/2008042011120047780
- https://www.mt.co.kr/stock/2008/10/15/2008101511101671229
- https://tilnote.io/pages/689b046edf13c4ef330e3e39
- https://m.cafe.daum.net/Antsstory/DJzh/152
- https://www.sisaon.co.kr/news/articleView.html?idxno=2026
- https://www.etoday.co.kr/news/view/1127429
- https://download.kiwoom.com/kiwoom_easy_help_new/5110.htm

**Not reachable (403 or blocked):** investors.com, the O'Reilly preview of *Trade Like an O'Neil Disciple*, the traders.com 1999 and 2006 pages, wikidocs, Bookmate. Anything taken from those is marked as a search snippet above. I could not get a full transcript of the original video.