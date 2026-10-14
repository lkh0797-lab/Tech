# 부록 — 차트 발굴 기법의 수치 근거와 검출 알고리즘 (2026-10-14)

- **대상 스펙**: `G:/내 드라이브/Claude/Tech/docs/2026-10-14-chart-techniques-design.md`
- **이 파일**: 처음엔 세션 스크래치 폴더 `<scratch>/research/addendum.md` 에 썼다
  - 세션이 끝나면 지워지는 스크래치 폴더다. 남길 내용은 `Tech/docs` 로 복사한다.
- **조사 노트** (같은 폴더)
  - 주제별 노트: `topicA_source_log.txt`, `topicB_fib_sources.txt`, `topicC_notes.md`, `topicD_notes.md`
  - 원문 텍스트 추출본:
    - `kiwoom_AdvancedSearch.txt` (키움 영웅문4 조건검색 도움말 PDF)
    - `bulkowski_top10.txt`, `bulkowski_eightbest.txt` (S&C 2011)
    - `arxiv1302.txt` (Penteado)
    - `lmw.txt` (Lo · Mamaysky · Wang)

---

## 0. 읽는 법과 공통 규칙

### 0.1 표기

| 표기 | 뜻 |
|---|---|
| **[H]** | 1차 출처(저자 본인 사이트 · 공식 도움말 · 논문 · 공개 코드). 수치를 그대로 옮겼다. |
| **[M]** | 충실한 2차 출처이거나, 서로 다른 출처 둘 이상이 일치한다. |
| **[L]** | 블로그 · 커뮤니티 수준이다. |
| **`구현 선택`** | 출처를 찾지 못했다. 값과 이유를 같이 적고 Config 상수로 둔다. |
| **[불코우스키 미국 통계]** | Bulkowski 의 미국 주식 표본에서 나온 수치다. 우리 데이터가 아니다. 맥락으로만 쓰고 확률로 화면에 쓰지 않는다(§11). |

- 원문 그대로의 인용은 저작권 때문에 이 문서 전체에서 **하나만** 쓴다(§9 청산 계획).
- 나머지 출처 내용은 모두 바꿔 쓴 요약이다. 숫자와 용어는 사실이므로 그대로 옮겼다.

### 0.2 모든 기법에 공통으로 적용하는 규칙

| 규칙 | 값 | 근거 |
|---|---|---|
| 양봉 | `C > O` (엄격). 같으면 양봉이 아니다. 도지는 연속을 끊는다. | 키움 조건검색 도움말 p.3: 시가보다 종가가 높게 끝난 봉. TA-Lib 은 `C ≥ O` 를 흰 봉으로 보지만 한국 HTS 기준을 따른다. [H] |
| 음봉 | `C < O` | 같은 곳 [H] |
| 비율 기준선 ("평균의 k배") | 오늘 봉을 **뺀** 직전 N봉 평균: `x.shift(1).rolling(N).mean()` | Bulkowski 는 돌파 거래량 평균에 돌파일을 넣지 않는다(glossary, volbkout). TA-Lib 캔들 평균도 직전 봉만 쓴다. [H] **예외**: 피보 매수 신호의 5일 거래량 이평은 키움 관례대로 오늘을 포함한다(§3). |
| 이동평균선 | 종가 단순이동평균(SMA)이며 오늘 봉을 포함한다(EOD 확정값). | Bulkowski 의 Kacher–Morales 검증이 SMA 를 썼다. TradingView 7-Week Rule 기본값도 10SMA 다. [M] |
| 가격 자료 | 수정주가(분할 · 무상 반영) 일봉 | 차트 업계 관행(Börse Frankfurt adjusted prices 설명). KRX 1차 문서는 찾지 못했다. [M] |
| 거래정지 행 | 거래량 0 인 행은 월봉 · 주봉 합성과 평균 계산에서 뺀다. | `구현 선택`. 이유: 공급자가 정지일을 직전 종가로 채우면 월 시가 · 저가와 평균이 왜곡된다. |
| 가격제한폭 체제 | 2015-06-15 부터 ±30%, 그 전은 ±15% | 이투데이 https://www.etoday.co.kr/news/view/1127429 [H]. % 문턱 규칙(+7%, −15%)은 이 변화에 민감하다. 그래서 상대 기준(몸통 배수)을 같이 둔다. |
| 신호 날짜 | 패턴을 완성한 봉의 날짜 | 확인 사건(안착 · 망치 확인 등)은 따로 기록하고 더 늦은 날짜를 단다. |
| 스윙 고점 · 저점 | 확인 봉이 지난 뒤에만 쓴다. | 스펙 전제 그대로 |
| 앞부분 불변 | 모든 t 와 T > t 에 대해, `detect(bars[:t+1])` 의 t 판정 = `detect(bars[:T])` 의 t 판정 | 모든 기법 테스트에 넣는다(§13). |

---

## 1. 스펙 변경 요약

| # | 스펙 위치 | 지금 | 바꿀 것 | 근거 등급 |
|---|---|---|---|---|
| 1 | §1 적삼병 정의 | 양봉 3개 | + 종가 상승 `C[k] > C[k−1]` 을 기본 요구 (`RTM_REQUIRE_HIGHER_CLOSE=True`). 월봉은 시가 ≈ 전월 종가라 거의 항상 저절로 충족된다. | H (출처 대부분 일치) |
| 2 | §1 바닥권 | −20% `구현 선택` | 값은 유지하고 근거(약세장 −20% 관례)를 단다. Bulkowski 연중 범위 위치를 맥락으로 덧붙인다. | M |
| 3 | §2 장대양봉 | +7% 이고 거래량 ×2 | + 몸통 ≥ 직전 15봉 평균 몸통 × 3, + 위 · 아래 꼬리가 각각 몸통보다 짧음 (Bulkowski Long White Day). +7% 와 ×2 는 `구현 선택` 으로 남긴다. | H(몸통 규칙) |
| 4 | §2 파동 저점 L | 직전 60봉 최저 | 직전 확정 스윙 고점 이후 최저(60봉 상한). 그런 고점이 없으면 60봉 최저. | L–M |
| 5 | §2 지지 판정 | ±1.5% 밴드 | 저가 ≤ 라인 × 1.015, 종가 ≥ 라인, 저가 > 다음 깊은 라인. 아래꼬리 관통을 허용하고, 스펙 원안은 옵션으로 둔다. | `구현 선택` |
| 6 | §2 매수 신호 | 거래량 > 5일 이평 | 키움식 '상향돌파'(전일 ≤, 당일 >)를 기본으로, 수준 비교는 옵션. 반등은 전일보다 높은 종가로 본다. 신호는 마지막 접촉 뒤 3봉 안이어야 한다. | M |
| 7 | §3 접점 허용 | ±1.5% | 선 아래 1.5% ~ 선 위 0.5% (관통 금지 허용치와 맞춘다) | L–M |
| 8 | §3 안착 확인 | 돌파일 종가 대비 +3% | **선 값 대비** +3% (Murphy · Edwards & Magee). '3일' 은 돌파일을 포함한 연속 종가 3개. | M–H |
| 9 | §3 단계 | 거래량 미달이면 버림 | '돌파(거래량 미달)' 관찰 단계를 추가한다. | M (출처 충돌) |
| 10 | 체크리스트 5 | 업종 RS 상위 ⅓ | 상위 ¼. Bulkowski 는 44업종 중 1–11위를 최상위로 보고, 6개월 평균 수익률로 순위를 매긴다. | H |
| 11 | 체크리스트 7 | 52주 고점까지 10% 미만이면 경고 | 가장 가까운 위 저항(확정 스윙 고점)까지 거리로 판정한다. 신고가면 '위 저항 없음'으로 통과. | H(항목) / `구현 선택`(%) |
| 12 | 체크리스트 8 | 손절 거리(%)만 표시 | + Bulkowski 변동성 손절(저가 − 2 × 22봉 평균 고저폭)보다 가까운 손절이면 경고 | H |
| 13 | 체크리스트 9 | 공시 JSON 에 의존 | 가격만으로 판정: 126봉 안에 하루 종가 −15% 이하(Bulkowski 데드캣 사건)가 있으면 경고. 공시 위험은 덧붙이는 꼬리표로 바꾼다. | H |
| 14 | 체크리스트 10 | '추격 금지' | '단기 급등 — 되돌림 뒤 진입 고려'. Bulkowski 자료끼리 엇갈리므로 금지가 아닌 주의로 낮춘다. | H(충돌) |
| 15 | 청산 계획 | 10일선 2단계 | + 7주(35거래일) 규칙과 50일선 안내 + Bulkowski 검증 결과 주석 | H/M |
| 16 | §5 10% 주도주 | 시가 대비 +10% | 시가 대비와 전일 대비를 둘 다 계산해서 보인다. 영상 요약이 기준을 밝히지 않아 시가 대비는 미검증이다. | L |

---

## 2. `red_three_monthly` — 월봉 적삼병

### 2.1 출처 요약

**정의**
- **한경 경제용어사전** (https://dic.hankyung.com/economy/view/?seq=5747) [H, 한국 관례]
  - 적삼병은 양봉 3일 연속이다.
  - 월간 기준으로 석 달 연속 양봉이면 추세적 강세장 진입으로 읽는다.
  - 종가 상승이나 꼬리 조건은 없다.
- **키움 도움말 p.39** (https://download.kiwoom.com/hero4_help_doc/KiwoomHero4_AdvancedSearch.pdf) [H]
  - 각 시가가 전날 몸통 안에서 나오고, 매일 새 고가를 만들며, 종가는 고가 근처다.
  - 바닥권이나 일정 기간 횡보 뒤에 나오면 반전 신호다.
  - 경고 변형으로 어드밴스 블록과 정체(스톨드) 적삼병을 따로 든다.
  - 그런데 분류상으로는 '상승추세 지속 캔들' 절에 넣어 두었다.
- **Bulkowski** (https://thepatternsite.com/ThreeWhiteSoldiers.html) [H]
  - 키 큰 흰 봉 3개, 종가는 고가 근처, 종가 상승, 몸통 겹침, 각 시가는 전 봉 몸통 안, 짧은 위꼬리.
  - 들어오는 추세는 하락이다.
- **TA-Lib** `ta_CDL3WHITESOLDIERS.c` (https://github.com/TA-Lib/ta-lib) [H, 코드]
  - 연속 상승 종가, 시가는 전 몸통 안 또는 근처, 위꼬리가 없거나 매우 짧음.
  - 코드 주석: Morris 는 긴 봉을 원하고 Nison 은 아니다.
- **같은 방향의 다른 출처** [M]
  - 종가 상승을 요구: 미래에셋 HTS 0544 (https://securities.miraeasset.com/kairos/0544.htm), 삼성증권 POP 1512 (http://www.samsungpop.com/contents/poptrading/help/1512.html), 野村 赤三兵 (https://www.nomura.co.jp/terms/japan/a/akasanpei.html).
  - 고가 · 저가 동시 상승을 요구: iFinance 赤三兵 (https://www.ifinance.ne.jp/learn/technical/twd068.html).
- **김정환 《차트의 기술》**: 목차만 확인했다. '월봉 적삼병' 항목을 책에서 찾지 못했으므로 **영상의 규칙**으로만 다룬다.

**출처가 엇갈리는 곳**
1. **최소 정의**: 한경은 양봉 3개만 요구한다. 나머지 대부분은 종가 상승까지 요구한다.
2. **몸통 크기**: Morris 와 Bulkowski 는 큰 몸통을 원하고, Nison 은 요구하지 않는다.
3. **위꼬리**: Bulkowski 와 TA-Lib 은 필수 조건으로, 일본 자료는 강도 등급으로 다룬다.
4. **맥락**
   - 키움과 Nison(2차 출처)은 바닥이나 횡보 뒤를, Bulkowski 는 하락 추세를 든다.
   - 그런데 Bulkowski 일봉 자료에서는 연중 **고점** ⅓ 안의 적삼병도 반전으로 자주 작동했다.
   - 따라서 '바닥권에서만' 이라는 조건은 한국 · 일본 관례다. 그의 통계가 받쳐 주는 규칙은 아니다.

### 2.2 파라미터

| 상수 | 값 | 근거 | 등급 |
|---|---|---|---|
| `RTM_N` | 3 | 한경(석 달 연속 양봉), 영상 [04:00–14:00] | H |
| 양봉 | `C > O` | 키움 p.3 | H |
| `RTM_REQUIRE_HIGHER_CLOSE` | `True` | Bulkowski, TA-Lib, Nison(2차), 미래에셋, 삼성, 野村. 월봉에서 이 조건이 결과를 바꾸는 경우는 월 경계에서 갭 하락이 난 때뿐이다. | H (광범위 일치) |
| `RTM_BOTTOM_DD` | 0.20 | 약세장 = 최근 고점 대비 20% 하락이라는 관례 (https://www.fool.com/investing/how-to-invest/bear-market.aspx). 캔들 문헌의 규칙은 아니다. | M |
| `RTM_BOTTOM_LOOKBACK` | 12 (저점 월 직전 완성 월 12개, 저점 월 제외) | 스펙 그대로 | — |
| `RTM_MAX_LAG` | 6 (셋째 양봉 ≤ 저점 월 + 6) | `구현 선택`. 저점 뒤 음봉 1~3개월을 거친 적삼병까지 허용하는 상한일 뿐이다. | — |
| `RTM_LOW_MONTH_AS_FIRST` | `False` | `구현 선택`. 스펙 문장 '확정 저점 **뒤**' 를 따른다. 저점 월을 첫 병정으로 셀지는 출처가 없다. | — |
| `RTM_DROP_ZERO_VOLUME` | `True` | `구현 선택` (§0.2) | — |
| 월 거래량 | `V_sum` (합)을 쓰고 `V_avg` (평균 일거래량)도 같이 둔다 | CSI Data 는 월 거래량 기본값을 평균 일거래량으로 설명하고 합은 선택으로 둔다 (https://csidata.com/custserv/onlinehelp/OnlineManual/structureofdailyweeklyandmont.htm). 두 관례 모두 유효하므로 화면에 '합'이라고 적는다. | M |

**관찰 꼬리표** (판정에는 쓰지 않는다)

| 꼬리표 | 정의 | 근거 | 등급 |
|---|---|---|---|
| `RTM_FLAG_SHORT_UPPER` | 세 봉 모두 `(H − C) < 0.1 × 직전 완성 월 10개의 평균 (H − L)` | TA-Lib ShadowVeryShort 기본값. Bulkowski 는 짧은 위꼬리를 요구한다. | M |
| `RTM_FLAG_ADV_BLOCK` (경고) | 셋째 몸통 < 둘째 몸통 − 0.6 × 직전 5개월 평균 (H − L), 또는 셋째 위꼬리 ≥ 셋째 몸통 | TA-Lib Far(0.6), 키움 어드밴스 블록 · 정체, iFinance 先詰まり · 思案星 | M |
| `RTM_FLAG_RISING_LOWS` | 세 봉 모두 `L[k] > L[k−1]` | iFinance, 미래에셋, 키움(매일 새 고가) | M |
| `RTM_YEARLY_POS` | `(C_sig − LL12)/(HH12 − LL12)` (신호 월까지 완성 월 12개). ⅓ 이하면 '연중 하단 ⅓' | Bulkowski glossary(연중 범위 = 직전 1년 최고 · 최저), https://thepatternsite.com/buylow.html | H (정의) |

### 2.3 검출 알고리즘 (일봉 EOD → 월봉, 미래 자료 없음)

입력은 기준일 T 까지의 수정 일봉이다.

1. 거래량 0 행을 지운다.
2. 달력 월(YYYY-MM)로 묶는다.
   - **완성 월** = 그 뒤 달의 일봉이 하나라도 있는 달이다. 따라서 마지막 묶음은 언제나 미완성(진행 중 달)이다.
   - 월말 마지막 거래일 장 마감 직후에도, 다음 달 첫 봉이 오기 전까지는 미완성으로 둔다. 하루 늦어지지만 앞부분 불변이 구조적으로 보장된다.
   - 거래소 휴장일 달력으로 당일 확정하는 방식은 `구현 선택` 옵션으로 둔다.
3. 월봉을 만든다: `O` = 첫 행 시가, `H` = 최대 고가, `L` = 최소 저가, `C` = 마지막 행 종가, `V_sum`, `V_avg`.
4. 완성 월에 0..n−1 번호를 매긴다. n−1 이 가장 최근 완성 월이다.
   - 행이 하나도 없는 달(장기 거래정지)이 끼면, 그 달을 건너서는 연속 판정도 저점 판정도 하지 않는다(`구현 선택`).
5. **양봉 런**: `bull[k] = C[k] > O[k]`.
   - 런의 시작 s = n−3 이고 `bull[n−3]`, `bull[n−2]`, `bull[n−1]` 이 모두 참이어야 한다.
   - `RTM_REQUIRE_HIGHER_CLOSE` 이면 `C[n−2] > C[n−3]` 이고 `C[n−1] > C[n−2]` 도 요구한다.
6. **확정 저점 m** (영상 정의 [08:00–09:00])
   - `L[m] < L[m−1]` 이고 `L[m] < L[m+1]`. m+1 이 완성 월이어야 저점이 확정된다.
   - 범위는 `m+1 ≤ s ≤ m + RTM_MAX_LAG − 2` 다. 즉 셋째 양봉 n−1 ≤ m+6.
   - `RTM_LOW_MONTH_AS_FIRST=True` 이면 s = m 도 허용한다.
7. **새 저가 없음**: `min(L[m+1..n−1]) > L[m]`.
8. **첫 런 조건**: m < k < s 인 어떤 k 에서도 `bull[k..k+2]` 가 모두 참이면 안 된다.
   - 그런 k 가 있으면 이미 앞서 신호가 났다는 뜻이다. 이 경우 '적삼병 이후 연속 양봉 N개월' 관찰로만 보인다.
9. 조건을 만족하는 m 이 여럿이면 `L[m]` 이 가장 낮은 달을 쓴다. 같으면 이른 달을 쓴다(`구현 선택`).
10. **바닥권**: m ≥ 12 이고 `L[m] ≤ (1 − RTM_BOTTOM_DD) × max(C[m−12..m−1])`.
    - 직전 완성 월 12개가 없으면 '바닥권 모름'으로 두고 신호를 내지 않는다(관찰 목록에만 둔다).
11. **신호** `red_three_monthly`: 신호 월은 n−1 이다.
    - n−1 이 '가장 최근 완성 월' 인 동안, 즉 다음 달 내내 신호가 유지된다.
12. **함께 보일 것**
    - §2.2 의 관찰 꼬리표.
    - 진행 중 달의 월초 시가 대비 등락. 라벨은 '이번 달 진행 · 미완성'. 영상의 가설 '다음 달도 양봉' 은 신호가 아니라 이것을 관찰하는 대상이다.
    - 월 거래량 합.
13. 스팩 · ETF · 리츠는 제외한다(스펙 그대로).

**HTS 와 대조할 때**
- 키움 '캔들연속발생 [월] 3봉 연속 양봉' 을 **0봉전** 으로 걸면 진행 중 달이 들어간다.
  - 도움말 p.3 에 따르면, 봉이 끝나기 전에는 현재가가 종가 역할을 하고 맨 오른쪽 봉이 0봉전이다.
- 우리 규칙과 같은 것은 **1봉전** 기준이다.
- 키움 조건에는 저점 확정, 바닥권, 종가 상승 조건이 없다.

**지수에 적용**: 시장 맥락 칸의 지수 월봉 적삼병도 1~12단계를 그대로 쓴다. 단 거래정지 처리와 제외 대상은 필요 없다.

---

## 3. `fib_pullback` — 피보나치 눌림 반등

### 3.0 먼저 알아둘 증거 (화면 문구에 반영)

- **StockCharts ChartSchool** Fibonacci Retracements (https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-annotation-tools/fibonacci-retracements) [H]
  - 흔히 쓰는 되돌림 수준은 23.6, 38.2, 50, 61.8 이다.
  - 이 수준들은 반전 가능성을 지켜보는 구역일 뿐이다. 캔들 · 거래량 · 모멘텀 같은 다른 신호로 확인해야 한다.
  - 50% 는 피보나치 비율이 아니다. 다우 이론에서 왔다.
- **Bulkowski 자동 검증** (2020, 489종목, 2009–2020 강세장, 스윙 창 2 · 5 · 10 · 20봉) (https://thepatternsite.com/SwingSetup.html) [H, 불코우스키 미국 통계]
  - 38 · 50 · 62% 되돌림이 1~100% 의 다른 값보다 더 자주 나오지 않았다.
  - 손으로 고른 표본에서는 되돌림 중앙값이 59% 였고 약 45% 가 61% 보다 깊었다 (https://thepatternsite.com/fib.html).
- **Tsinaslanidis · Guijarro · Voukelatos** (Expert Systems with Applications 187, 2022, https://doi.org/10.1016/j.eswa.2021.115893) [H, 초록 수준]
  - 피보나치 구역 안의 가격 행동은 다른 구역과 통계적으로 다르지 않았다.
  - 구역을 넓히면 반등 횟수가 기계적으로 늘어난다.

→ 화면에서 라인은 '관심 구간' 으로만 부른다. 확률은 표기하지 않는다. 확인 조건(양봉 + 거래량)은 필수다. 접촉 허용치를 적중률이 가장 높게 나오도록 튜닝하지 않는다.

### 3.1 파라미터

**기준 파동의 시작 — 장대양봉 (`LB_*`, `trendline_fib` 를 뺀 피보 계열 공통)**

| 상수 | 값 | 근거 | 등급 |
|---|---|---|---|
| `LB_WHITE` | `C > O` | 키움 p.31(장대봉), 미래에셋 0544 | H |
| `LB_MIN_CHG` | 0.07 (`C/C[−1] − 1`) | 한국 관례 블로그: 가격제한 15% 시절에는 7%, 30% 시절에는 10~15% 를 기준봉으로 본다 (https://i-whale.com/entry/기준봉이란-기준봉-선정하고-매매-종목-찾기 , https://jungbosum.com/주식-공부-차트-보는-법-장대양봉-역망치/). 0.10 옵션을 둔다. | L (`구현 선택` 성격 유지) |
| `LB_BODY_REL_K`, `LB_BODY_REL_N` | 3.0, 15 | Bulkowski Long White Day: 몸통이 최근 2~3주 평균 몸통의 최소 3배 (https://thepatternsite.com/LongWhiteDay.html). N=15 는 3주 ≈ 15거래일로 환산한 `구현 선택` 이다(10 도 쓸 수 있다). 후보가 너무 드물면 2.0 / 22 로 바꾼다 (Bulkowski TallCandleSAR: 직전 22거래일 평균의 2배 넘는 몸통, https://thepatternsite.com/TallCandleSAR.html). | H(규칙) / M(N) |
| `LB_SHADOW_LT_BODY` | `(H−C) < (C−O)` 이고 `(O−L) < (C−O)` | Bulkowski Long White Day: 꼬리가 몸통보다 짧다 | H |
| `LB_VOL_MULT`, `LB_VOL_N` | 2.0, 20 (직전 20봉, 당일 제외) | `구현 선택`. ×2 의 출처는 없다. 참고로 Bulkowski 는 '대량 거래' 를 30일 평균 대비로 본다 (https://thepatternsite.com/volbkout.html). | — |

- 키움 도움말 p.31 의 장대봉은 시가→종가 움직임이 이전 날들의 몸통보다 긴 봉이다. 숫자는 없다. 상대 몸통 기준이 HTS 정의와도 맞는다는 뜻이다.
- **측정 기준이 다르다**: 스펙의 +7% 는 전일 종가 대비 등락률이고, HTS 와 Bulkowski 는 시가→종가 몸통으로 잰다.
  - 갭 상승 뒤 몸통이 작은 봉은 스펙 기준만 통과한다. 그래서 몸통 조건을 같이 건다.
  - 몸통 조건은 2015년 가격제한폭 변화와 대형 · 소형주 변동성 차이에도 흔들리지 않는다.

**스윙과 라인**

| 상수 | 값 | 근거 | 등급 |
|---|---|---|---|
| `FIB_SWING_CONFIRM` | `'video'` (기본) / `'fractal2'` | 영상 [19:00–20:00]: 고점 봉 뒤에 음봉이나 종가 하락 봉이 나와야 한다. `fractal2` 는 좌우 2봉 (MetaTrader 5 fractals 도움말 https://www.metatrader5.com/en/terminal/help/indicators/bw_indicators/fractals). | M |
| `FIB_H_MAX_BARS` | 20 | `구현 선택`. 20봉 넘게 확정 없이 오르면 '한 파동' 이 아니라 추세다. 설정을 만료로 정리한다. | — |
| `FIB_L_MODE` | `'since_swing_high'` (기본) / `'min_lookback'` (스펙 원안) | tilnote 영상 요약: 장대양봉 직전 저점에서 장대양봉 고점까지 그린다 (https://tilnote.io/pages/689b046edf13c4ef330e3e39). 60봉 최저는 파동과 무관한 더 깊은 옛 저점을 잡아 라인을 너무 낮출 수 있다. | L–M |
| `FIB_L_LOOKBACK` | 60 | `구현 선택` (스펙 값) | — |
| `FIB_LEVELS_BUY` | 0.236, 0.382, 0.5 | ChartSchool 의 공통 수준. StockCharts mailbag 2009: 23.6 은 얕음, 38.2~50 은 보통, 61.8 은 깊음 (https://stockcharts.com/articles/mailbag/2009/05/using-the-fibonacci-retracements-tool.html). tilnote: 매수 후보는 23.6 · 38.2 · 50 이고 61.8 은 제외. | H |
| `FIB_LEVEL_INVALID` | 0.618 (표시 + 무효선) | ChartSchool. Bulkowski 매매 도움말: 상승 뒤 62% 넘게 되돌리면 하락 신호이므로 매도 (https://thepatternsite.com/tradehelp.html). | H |
| `FIB_SHOW_786` | `False` | 0.786 은 ChartSchool 에 없다. Elliott Wave International 튜토리얼(재게재 https://www.marketcalls.in/trading-lessons/learn-how-to-apply-fibonacci-retracements-to-your-trading.html)은 2파가 흔히 .618, 때로 .786 까지 되돌린다고 한다. | M |
| 라인 계산 | `lv(r) = H − r·(H − L)`. H = 고점 봉의 고가, L = 저점 봉의 저가(꼬리 기준) | ChartSchool ZigZag: 캔들 차트에서는 고저 범위로 스윙을 잰다 (https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/zigzag) | H |

**지지와 신호**

| 상수 | 값 | 근거 | 등급 |
|---|---|---|---|
| `FIB_TOL` | 0.015 | `구현 선택`. 권위 있는 수치 허용치가 없다. Bulkowski(https://thepatternsite.com/pullbacks.html)는 '근처' 를 판단에 맡기고, 키움 근접률은 사용자가 ±N% 를 정한다. 고정된 작은 값으로 두고 최적화하지 않는다. | — |
| `FIB_TOUCH_MODE` | `'wick'` (기본) / `'band'` (스펙 원안) | `wick`: 저가 ≤ lv×(1+tol), 종가 ≥ lv, 저가 > 다음 깊은 라인. `band`: lv×(1−tol) ≤ 저가 ≤ lv×(1+tol), 종가 ≥ lv. 이유: ChartSchool 예시는 라인 근처에서 긴 아래꼬리 망치가 나오는 경우다. `band` 는 꼬리가 1.5% 넘게 찌르고 되돌아온 정상적인 지지를 놓친다. | `구현 선택` |
| `FIB_SIGNAL_WINDOW` | 3 (마지막 접촉 봉 포함, 그 뒤 3봉까지) | ChartSchool 캔들 반전은 1~3일 안에 확인한다 (https://chartschool.stockcharts.com/table-of-contents/chart-analysis/candlestick-charts/candlestick-bullish-reversal-patterns) | M |
| `FIB_VOL_MA` | 5, 오늘 포함: `MA5V_t = mean(V[t−4..t])` | 키움 이동평균 관례 | H |
| `FIB_VOL_TEST` | `'cross'` (기본): `V_t > MA5V_t` 이고 `V_{t−1} ≤ MA5V_{t−1}`. `'level'` (스펙 원문): `V_t > MA5V_t`. | 키움 도움말: 돌파 = 기준값을 아래에서 위로 뚫는 것(앞 봉 A ≤ B, 현재 봉 A > B). '현재 거래량이 N일 평균거래량을 상향돌파' 예시는 거래량 1이평과 N이평의 골든크로스다. 영상의 '뚫는' 은 cross 다. 수학적으로 `V_t > MA5V_t` 는 `V_t > mean(V[t−4..t−1])` 과 같다. | M |
| `FIB_REQUIRE_UP_CLOSE` | `True` (`C_t > C_{t−1}`) | `구현 선택`. '반등' 양봉이라는 말을 따른다. ChartSchool 은 거래량이 실린 상승을 강세 확인으로 본다. | — |
| 진입 | 신호 봉 종가 | tilnote: 신호 캔들 종가에 매수. KRX 장후 시간외 종가 매매(15:40–16:00, 주문은 15:30 부터)로 실제 체결할 수 있다. 키움 도움말 1337 (https://download.kiwoom.com/hero4_help_new/1337.htm). | M |

**손절 · 무효 · 단계**

| 항목 | 값 | 근거 | 등급 |
|---|---|---|---|
| 1차 손절 | 활성 라인의 다음 깊은 라인 (23.6→38.2, 38.2→50, 50→61.8) | BabyPips 피보 손절 방법 1: 다음 피보 수준 바로 너머 (https://www.babypips.com/learn/forex/placing-stops-with-fibs) | H (관례) |
| 함께 표시 | 진입가 −7% (`FIB_STOP_ALT_PCT=0.07`), 스윙 저점 L, 체크리스트 8 의 변동성 손절 | O'Neil 7~8% 손절 (MarketSmith India, https://tradingqna.com/t/why-you-should-pay-close-attention-to-the-5-buy-zone-after-a-breakout-updated/95357). BabyPips 방법 2(스윙 저점). Bulkowski stops. | M |
| 무효 | 종가 < `lv(0.618)` 또는 저가 < L | Bulkowski tradehelp(62% 넘는 되돌림이면 매도). Elliott 규칙에서 2파는 1파를 100% 넘게 되돌리지 않는다(EWI) — 이것이 L 붕괴다. 학술 구현(https://pmc.ncbi.nlm.nih.gov/articles/PMC8752186/)도 61.8% 아래로 내려가면 청산한다. | M |
| `FIB_APPROACH_PCT` | 0.03 ('눌림 진행' = 라인 위 3% 안) | `구현 선택` (출처 없음) | — |
| `FIB_EXTENDED_PCT` | 0.05 (신호 종가보다 5% 넘게 오르면 '이격') | O'Neil/IBD 에서 매수점 위 5% 를 넘으면 이격(extended)으로 보는 것을 빌려 왔다 (위 MarketSmith India 글) | M |
| `FIB_SETUP_EXPIRY` | 30봉 (H 확정 뒤 신호 없이) | `구현 선택`. Bulkowski 용어집은 되돌림(throwback)을 30일 안의 복귀로 정의한다. 그와 같은 크기로 잡았다. | — |

- **위험 표시**: Bulkowski 의 되돌림 중앙값은 59% 다. 그렇다면 23.6 · 38.2 진입에서 다음 라인 손절은 자주 걸린다. 이 점을 우위가 아니라 **위험**으로 보인다.

### 3.2 검출 알고리즘

종목마다 상태 기계를 돌린다. 각 봉 t 에서는 t 까지의 자료만 쓴다.

상태는 `NONE → CANDIDATE → CONFIRMED → SIGNAL → (EXTENDED · STOPPED)` 로 진행하고, 끝 상태로 `INVALID` · `EXPIRED` 가 있다.

**미리 계산할 값** (모두 t 까지의 자료)
- `body = C − O`
- `avgBody15[t] = mean(|body|[t−15..t−1])`
- `avgV20[t] = mean(V[t−20..t−1])`
- `MA5V[t] = mean(V[t−4..t])`

**1. NONE → CANDIDATE**
- 봉 b 가 §3.1 의 장대양봉 조건(`LB_WHITE`, `LB_MIN_CHG`, `LB_BODY_REL`, `LB_SHADOW_LT_BODY`, `LB_VOL`)을 모두 만족하면 CANDIDATE 가 되고, trigger = b 다.
- L 을 정하고 이후로 고정한다.
  - `'since_swing_high'`: p+2 ≤ b 이고 b − p ≤ `FIB_L_LOOKBACK` 인 가장 최근 fractal-2 고점 p 를 찾는다. 조건은 `H[p] > H[p−2], H[p−1], H[p+1], H[p+2]` 다. 그러면 `L = min(Low[p+1..b])`.
  - 그런 p 가 없으면 `L = min(Low[b−60..b])`.

**2. CANDIDATE** (t ≥ b)
- `H = max(High[b..t])`, h = 그 고가가 처음 나온 봉. 장대양봉 자신의 고가도 H 가 될 수 있다(tilnote).
- 확정, `'video'`: t > h 이고 `High_t ≤ H` 이고 (`C_t < O_t` 또는 `C_t < C_{t−1}`) 이면 CONFIRMED, c = t.
  - t > h 이므로 장대양봉 당일에는 확정되지 않는다. 스펙의 '장대양봉 당일은 고점 아님' 이 이것이다.
- 확정, `'fractal2'`: t = h+2 이고 `High[h+1], High[h+2] < H` 이고 `H > High[h−1], High[h−2]` 이면 c = t.
- t − b > `FIB_H_MAX_BARS` 인데 아직 확정되지 않았으면 EXPIRED.
- `Low_t < L` 이면 INVALID.

**3. CONFIRMED**
- c 에서 라인을 고정한다: `lv(r)`, r ∈ {0.236, 0.382, 0.5, 0.618} (`FIB_SHOW_786` 이면 0.786 도).
- 각 봉 t ≥ c 에서 아래 순서로 판정한다.
  - a. `High_t > H` 이면 CANDIDATE 로 돌아간다. H 와 h 를 t 로 갱신하고, b 와 L 은 그대로 두고, 접촉 기록은 지운다.
  - b. `C_t < lv(0.618)` 또는 `Low_t < L` 이면 INVALID.
  - c. **접촉 검사**: 매수 라인을 가장 깊은 것부터 본다. 처음 만족하는 r 에 대해 `touch_bar = t`, `active_r = max(active_r, r)` 로 둔다.
    - `'wick'`: `Low_t ≤ lv(r)(1+FIB_TOL)` 이고 `C_t ≥ lv(r)` 이고 `Low_t > lv(r_next)`. r_next 는 다음 깊은 라인이며 0.5 의 다음은 0.618 이다.
    - `'band'`: `lv(r)(1−FIB_TOL) ≤ Low_t ≤ lv(r)(1+FIB_TOL)` 이고 `C_t ≥ lv(r)`.
  - d. **신호 검사**: 다음을 모두 만족하면 **SIGNAL** 이다.
    - touch_bar 가 있고 `0 ≤ t − touch_bar ≤ FIB_SIGNAL_WINDOW`. 접촉 당일 반등도 허용한다.
    - `C_t > O_t`
    - `FIB_REQUIRE_UP_CLOSE` 이면 `C_t > C_{t−1}`
    - `C_t ≥ lv(active_r)`
    - 거래량 검사(`FIB_VOL_TEST`)
    - 이때 `entry = C_t`, `stop = lv(next(active_r))` 다. −7% 값과 L 도 함께 보인다.
  - e. d 가 아니고, `lv(r) < C_t ≤ lv(r)(1+FIB_APPROACH_PCT)` 인 매수 라인 r 이 있으면 '눌림 진행(라인 접근)'.
  - f. t − c > `FIB_SETUP_EXPIRY` 이면 EXPIRED.

**4. SIGNAL 뒤** (t > t_s)
- `Low_t < stop` 이면 STOPPED. 재현 채점의 체결가는 `min(O_t, stop)` 로 둔다(갭 하락 반영, `구현 선택`).
- `C_t > entry × (1 + FIB_EXTENDED_PCT)` 이면 '이격'.
- 무효 규칙 b 도 계속 표시한다.

**5. 한 종목에는 진행 중인 설정이 하나뿐이다**
- CANDIDATE 중에 새 장대양봉이 나오면 흡수한다. H 는 계속 갱신하고 L 은 그대로 둔다.
- CONFIRMED 중의 새 장대양봉은 3a(신고가)나 3d(신호)로 처리된다.
- SIGNAL · INVALID · EXPIRED 뒤에는 새 trigger 로 새 설정을 연다. 앞 설정은 기록에 남긴다.

**화면 단계 이름** (스펙 그대로): '눌림 진행' = 3e, '신호' = 3d 당일, '이격' = 4. 61.8% 선은 '무효선' 으로 표시한다.

---

## 4. `trendline_break` — 빗각(하향) 추세선 돌파

### 4.1 출처 요약

**Bulkowski**
- 하향 추세선 (https://thepatternsite.com/trenddown.html) [H]
  - 돌파는 처음으로 종가가 선 위에 마감한 때다.
  - 선은 고점들을 따라 로그 눈금으로 그린다. 로그 눈금이 추세 변화를 더 일찍 보여 준다.
  - 특징별 성과는 §11 에 있다.
- QTL · QUTL (https://www.thepatternsite.com/QTL.html , https://thepatternsite.com/QUTL.html) [H]
  - 접점은 소고점(minor high)이어야 한다. 선이 가격을 자르는 곳은 접점이 아니다.
  - 접점이 둘뿐인 선은 약하다. 길수록, 접점이 많을수록, 간격이 넓을수록 좋다(수치는 없다).
  - 상승선은 접점 3개 이상, 약 30° 의 완만한 선이 오래간다. 다만 눈금에 따라 각도가 바뀌므로 각도를 그대로 쓸 수는 없다.
- 소고점 정의 (https://thepatternsite.com/minorhl.html): 고점 주변 5일 창(좌우 2봉)에 더 높은 가격이 없는 봉. [H]
- 상승 추세선 (https://thepatternsite.com/uptrendlines.html): 그의 소프트웨어는 소저점을 확신하려고 그 뒤 3봉을 기다린다. [H]
- 1-2-3 추세 전환 (https://thepatternsite.com/123tc.html, Victor Sperandeo 방법): 가장 높은 고점에서 시작해, 가장 낮은 저점이 지날 때까지 가격을 자르지 않도록 긋는다. [H]
- 거래량 연구 (https://www.thepatternsite.com/VolumeStudy.html) [H]
  - 대량 돌파는 평균 상승이 조금 높지만 되돌림이 훨씬 잦다.
  - 표본은 사각형과 쌍봉 · 쌍바닥이다. **추세선은 다루지 않는다.**

**알고리즘 연구**
- Lo · Mamaysky · Wang (2000, NBER w7613, https://www.nber.org/system/files/working_papers/w7613/w7613.pdf) [H]
  - 패턴이 완성된 뒤 3일 지연(d=3)을 두어, 미래 정보 없이 조건부 수익을 쟀다.
  - 쌍봉의 두 고점을 '같다' 고 보는 허용치는 1.5% 다.

**일반 규칙 (Murphy · ChartSchool)**
- Murphy 의 10가지 법칙 중 5번 (ChartSchool https://chartschool.stockcharts.com/table-of-contents/overview/john-murphys-10-laws-of-technical-trading) [H]: 유효한 추세선은 최소 3번 닿는다. 오래 버티고 많이 시험될수록 중요하다.
- ChartSchool Trend Lines (https://chartschool.stockcharts.com/table-of-contents/chart-analysis/trend-lines) [H]
  - 두 점이 선을 만들고 셋째 점이 확인한다.
  - 가파를수록 덜 유효하다. 간격은 고른 편이 좋다.
  - 튀는 봉은 어느 정도 무시할 수 있다. 반로그 눈금을 권한다.

**돌파 확인 필터**
- Penteado (arXiv 1302.1228, https://arxiv.org/pdf/1302.1228; Murphy 1986 pp.66–67, 74 인용) [M]
  - 반전 확인은 셋 중 하나다: 종가가 선 밖 3% 이상, 다음 2일에 걸쳐 3% 누적, 교차 뒤 3봉이 선 밖에 머묾.
  - 두 앵커 고점은 3봉 이상 떨어져 있어야 한다.
- Edwards & Magee (Peter Brandt 경유 https://www.peterlbrandt.com/?p=12076) [M]: 결정적 돌파는 가격의 약 3% 만큼 선 밖에서 마감한다. 상향 돌파에는 거래량이 늘어야 한다.
- TigerShark(Andy Swan 2007, http://www.tigersharktrading.com/articles/8406/1/When-Is-a-Trendline-Break-Valid/Page1.html) [M]: 장기선 3%, 단기 매매 1%, 2일 연속 종가 규칙.

**국내 출처**
- 김정환 《차트의 기술》 교보 e북 미리보기 (https://ebook-product.kyobobook.co.kr/dig/epd/sam/E000003218169)
  - 추세선은 종가만 이어서는 안 되고 장중 고가 · 저가를 포함해 그어야 한다.
  - 장중 관통이 나오면 옛 선과 새 선을 함께 그어 두고 이후 가격으로 판단한다.
  - 진짜 이탈을 판단할 기준이 필요하다고 쓰지만, 미리보기는 그 기준 직전에서 끝난다.
  - 영상의 9일<9주<9개월, 접점 3개 vs 8개, 3~4일 · 3~4% 는 책에서 확인하지 못했다(§14).
- 키움 조건검색에는 추세선 조건이 아예 없다.

**O'Neil 돌파 거래량** [M]
- 평균보다 40~50% 이상 많아야 한다. 출처: MarketSmith India (검색 요약), LuxAlgo O'Neil base analysis (https://www.luxalgo.com/library/concept/oneil-base-analysis.md), DSIJ (50일 평균 대비 50%).
- 모두 베이스(base) 돌파 기준이다. 추세선용은 아니다.

### 4.2 파라미터

| 상수 | 값 | 근거 | 등급 |
|---|---|---|---|
| `TL_PIVOT_K` | 3. 소고점 p: `H[p] ≥ max(H[p−3..p−1])` 이고 `H[p] > max(H[p+1..p+3])` (같은 값은 왼쪽 봉이 이긴다). 봉 p+3 부터 쓸 수 있다. | Bulkowski 정의는 좌우 2봉, 그의 소프트웨어는 3봉 대기, LMW 는 d=3, Pine `ta.pivothigh` 는 오른쪽 봉들이 지난 뒤에야 값이 나온다 (https://pineify.app/pine-script/reference/ta/pivothigh). k ∈ {2, 3} 을 설정으로 둔다. | H(지연) / M(k) |
| `TL_PRICE_SCALE` | `'log'`: y = ln(High), x = 거래일 봉 번호 | Bulkowski trenddown · uptrendlines, ChartSchool 반로그, neurotrader 코드 | H |
| `TL_LOOKBACK` | 250봉 | `구현 선택`. 영상의 9개월 단계(~189봉)를 품고, Bulkowski 중앙 길이 44~48일보다 충분히 길다. trendln 기본값 125 는 참고만 했다. | — |
| `TL_ANCHOR_MODE` | `'highest'` (기본) / `'volume'` / `'both'` | Sperandeo 1-2-3(Bulkowski 123tc · QTL): 가장 높은 고점. 영상 [21:00]: 거래량 터진 봉의 고점. **충돌**: AAII(https://www.aaii.com/journal/article/rules-for-drawing-and-analyzing-trendlines)는 헛신호를 줄이려고 극단 고점보다 둘째 고점을 권한다. | M |
| `TL_ANCHOR_VOL_MULT` | 2.0 × 직전 50봉 평균 거래량(당일 제외) | `구현 선택` | — |
| `TL_TOL_CUT` | 0.005: A..t−1 모든 봉에서 `High ≤ 선 × 1.005` | 엄격한 쪽(Bulkowski · neurotrader 허용치 1e-5 · 김정환의 장중 고가 포함)과 관대한 쪽(ChartSchool 의 튀는 봉 무시, AAII 의 작은 위반 허용) 사이에서 고른 `구현 선택` | — |
| 종가 관통 금지 | A..t−1 모든 봉에서 `C ≤ 선` | Bulkowski 의 '처음으로 선 위에 마감한 종가' 정의에서 나온다. 그 전에 선 위 종가가 있었다면 돌파는 이미 지난 일이고 후보는 낡았다. | H |
| `TL_TOL_TOUCH_BELOW` | 0.015: 접점 = 확정 소고점 중 `선×0.985 ≤ High ≤ 선×1.005` | 소고점 요구는 Bulkowski QTL. 1.5% 는 LMW 쌍봉 허용치를 빌린 것이다. 위쪽을 0.5% 로 묶은 것은 관통 금지 허용치와 맞추기 위해서다. | H(소고점) / L–M(1.5%) |
| `TL_MIN_TOUCHES` | 3 (앵커 포함) | Murphy 법칙 5, ChartSchool, Bulkowski QUTL | H |
| `TL_BONUS_TOUCHES` | 5 | Bulkowski 상승선 매매 검증(접점이 많을수록 성과 증가, §11). 영상의 '8접점' 은 출처를 찾지 못했다. | M |
| `TL_MIN_GAP` | 10봉 (이웃 접점 사이) | `구현 선택`. 출처가 있는 최소값은 Penteado 의 3봉뿐인데, k=3 소고점이면 자동으로 충족된다. | — |
| `TL_WIDE_GAP` | 13 (접점 간격 중앙값이 13봉을 넘으면 가점) | Bulkowski trenddown 중앙값 13일(상승선 12일). 효과는 작다. | M |
| `TL_MIN_LEN` | 40봉 (t − A) | `구현 선택` (스펙 값). Bulkowski 표본 길이 중앙값(48)의 바로 아래다. 후보가 너무 줄면 20~30 으로 낮추고 길이 가점에 맡긴다. | — |
| `TL_LONG_LEN` | 48 (넘으면 가점) | Bulkowski trenddown 중앙값 48일(상승선 44일) | M |
| 기울기 등급 | b (ln/봉)를 %/봉 = e^b − 1 로도 보인다. '완만' = 그날 **이전** 250거래일 동안 검출된 선들의 \|b\| 중앙값 이하. 가중치는 가장 크게 준다. | Bulkowski 의 중앙값 분할 방식을 따른다(§11). 그의 문턱 0.05 는 달러/일 단위라 원화 주가에 옮길 수 없다. 과거 검출만 쓰므로 앞부분 불변을 지킨다. | H(방향) / `구현 선택`(문턱) |
| 진입 추세 (선택 가점) | 앵커 직전 20봉의 ln(종가) OLS 기울기가 0 근처 | Bulkowski trenddown: 평평한 진입 추세가 낫다. 20봉과 문턱은 `구현 선택`. | M |
| 거래량 추세 | [A, t−1] 거래량 OLS 기울기 < 0 이면 가점. 관문으로는 쓰지 않는다. | Bulkowski glossary(패턴 시작부터 끝까지 회귀), trenddown(효과 매우 작음) | M |
| `TL_VOL_MULT`, `TL_VOL_N` | 1.5, 50 (당일 제외). 필수 유지(스펙). | O'Neil 40~50%, Edwards & Magee. **반대 증거**: Bulkowski 거래량 연구(§11). 그래서 버리지 않고 '돌파(거래량 미달)' 로 남긴다. | M (충돌) |
| `TL_SHOW_LOWVOL_BREAK` | `True` | 위 충돌 때문에 조용히 버리지 않는다 | — |
| 돌파 | `C[t] > 선(t)` 이고 `C[t−1] ≤ 선(t−1)`. 장중 고가만 넘은 경우는 돌파가 아니다. | Bulkowski(첫 종가), 키움 돌파 정의(앞 봉 ≤, 현재 봉 >), TigerShark(종가가 더 중요), 김정환(장중 관통은 판단이 어렵다) | H |
| `TL_CONF_PCT` | 0.03, **그날의 선 값 대비** | Murphy(Penteado), Edwards & Magee(Brandt), TigerShark 모두 선을 기준으로 잰다. 스펙의 '돌파일 종가 +3%' 는, 돌파 종가가 이미 선보다 2% 위면 선 대비 약 5% 를 요구하게 된다. 어느 출처보다 엄격하다. | M–H |
| `TL_CONF_BARS` | 3: 돌파일을 포함해 연속 3 종가가 선 위 | Penteado(3봉), 영상(3~4일). Murphy 2일 규칙을 쓰려면 2. '돌파 **뒤** 3일' 을 돌파일 제외로 읽으면 4 가 되는데, 이는 영상 상한 4일과 같다. | M |
| `TL_NEAR_PCT` | 0.02 ('돌파 임박' = 선 아래 2% 안) | `구현 선택`. 접점 허용치와 같은 크기다. | — |
| `TL_HAMMER_WINDOW` | 20 (돌파 전 20봉 안의 망치형) | `구현 선택` (스펙 값) | — |
| `TL_DISPLAY_BARS` | 20 (안착 확인 뒤 '돌파' 를 표시하는 기간) | `구현 선택` | — |
| 목표가 (표시만) | T1 = 앵커 A 의 고가. T2 = 돌파가 + 0.56 × D. D = 마지막 접점 이후 [p_last, t0] 에서 `선(i) − Low[i]` 의 최대값(가격 단위). | Bulkowski trenddown 측정 규칙과 '선 시작 가격 도달' 통계(§11). 화면에는 '불코우스키 측정 규칙(미국)' 이라고 적는다. | M |

### 4.3 망치형 (관찰 꼬리표; 공용 함수 `is_hammer(j)`)

**출처**
- Nison: 원서는 확인하지 못했다. 2차 전사본만 봤다.
- StockCharts 강세 반전 패턴 (위 ChartSchool URL)
- Bulkowski Hammer (https://thepatternsite.com/Hammer.html)
- TA-Lib `ta_CDLHAMMER.c`
- 키움 p.35 (해머 = 양봉 망치형)
- 한경 (https://dic.hankyung.com/economy/view/?seq=10062)
- 삼성 POP 1512

**파라미터**

| 상수 | 값 | 근거 | 등급 |
|---|---|---|---|
| `HM_LOWER_X` | `lower ≥ 2.0 × body`. `lower = min(O,C) − L`, `body = |C−O|`, `H > L` 필요 | Nison(2차), StockCharts(몸통의 최소 2배), Bulkowski(2~3배의 아래쪽 값), 삼성(2배 이상 분류) | H |
| `HM_UPPER_X` | `upper = H − max(O,C) ≤ 0.1 × mean(H−L, 직전 10봉)` | TA-Lib ShadowVeryShort 가 '위꼬리 없거나 매우 짧음' 을 수치로 만든 것 | M |
| `HM_RANGE_REL` | `(H−L) ≥ 1.0 × mean(H−L, 직전 10봉)` | StockCharts: 최근 10~20일보다 범위가 크다. 1.0 은 `구현 선택`. | M |
| `HM_PRIOR_DECLINE` | `C[j−1] < EMA20[j−1]` | StockCharts: 20일 지수이평 아래 거래를 하락으로 볼 수 있다. Bulkowski: 들어오는 추세는 하락. | M |
| `HM_YEARLY_POS_MAX` | `(C_j − LL252)/(HH252 − LL252) ≤ 1/3`. HH · LL 은 j−251..j | Bulkowski: 연중 저점에서 ⅓ 안이 가장 좋다 | H (정의) |
| `HM_WHITE` | 꼬리표만 붙인다(`C > O` 이면 '양봉 망치') | Bulkowski · 한경은 양봉이 낫다고 보고, Nison 은 색이 중요하지 않다고 본다. 키움은 '양봉 망치형' 이라는 이름을 쓴다. | M |
| `HM_CONFIRM_BARS` | 3: 그 뒤 3봉 안에 `C > H_j` 이면 '망치 확인' (별도 날짜) | StockCharts 1~3일. Bulkowski 의 돌파 = 캔들 위로 마감한 종가. | M |
| 도지 (몸통 0) | 허용하고 'doji-hammer' 라벨을 붙인다 | `구현 선택`. TA-Lib 식도 허용한다. | — |

- 스펙의 '바닥권 망치형' 은 `HM_PRIOR_DECLINE` 과 `HM_YEARLY_POS_MAX` 를 둘 다 만족하는 경우다.

### 4.4 검출 알고리즘 (종목마다, 완성 봉 t 에서)

**동결된 선이 없을 때**

1. **확정 소고점 집합**
   - `P_t = { p : t − TL_LOOKBACK ≤ p, p + k ≤ t − 1, p 는 §4.2 의 소고점 }`.
   - `p + k ≤ t − 1` 이므로 선은 t−1 까지의 자료만으로 정해진다. 그 뒤에 봉 t 의 종가를 시험한다.
2. **앵커 후보**
   - `'highest'`: `argmax_{p∈P_t} H[p]`.
   - `'volume'`: `V[p] ≥ 2.0 × mean(V[p−50..p−1])` 인 p 들.
3. **각 앵커 A 에 대해 가장 낮게 붙는 선**
   - `b* = max_{i ∈ (A, t−1]} ( ln H[i] − ln(1+TL_TOL_CUT) − ln H[A] ) / (i − A)`
   - 선은 `ℓ(i) = ln H[A] + b*·(i − A)` 다.
   - 앵커에서 선을 내려 돌리다가 처음 닿는 데서 멈추는 Sperandeo 식 작도와 같다. 이렇게 하면 (A, t−1] 의 모든 고가가 `선 × 1.005` 이하가 된다. 계산량은 앵커당 O(n).
   - `b* ≥ 0` 이면 하향선이 아니므로 버린다.
4. **종가 관통 검사**: i ∈ [A, t−1] 중 하나라도 `C[i] > exp(ℓ(i))` 이면 낡은 선이므로 버린다.
5. **접점 세기**: T = [A] 로 시작한다.
   - 시간 순서로 p ∈ P_t, p > A 를 본다.
   - `ℓ(p) − ln(1+TL_TOL_TOUCH_BELOW) ≤ ln H[p] ≤ ℓ(p) + ln(1+TL_TOL_CUT)` 이고, `p − (마지막으로 받은 접점) ≥ TL_MIN_GAP` 이면 접점으로 받는다(`구현 선택`: 앞에서부터 탐욕적으로).
6. **유효한 선**: `|T| ≥ TL_MIN_TOUCHES` 이고 `t − A ≥ TL_MIN_LEN` 이고 `b* < 0`.
7. **최선 선 고르기**: 유효한 선 중에서 (접점 수, 길이, −|b*|) 순서로 가장 큰 것을 고른다. Bulkowski QTL 은 접점이 많은 선을 우선한다.
8. **돌파 검사**: `C[t] > exp(ℓ(t))` 이고 `C[t−1] ≤ exp(ℓ(t−1))` 이면 다음과 같이 한다.
   - `vr = V[t] / mean(V[t−50..t−1])` 를 계산한다.
   - `vr ≥ TL_VOL_MULT` 면 단계 '안착 확인 중' 이고 t0 = t 다.
   - 아니면 `TL_SHOW_LOWVOL_BREAK` 에 따라 '돌파(거래량 미달)' 관찰로 남긴다.
   - 어느 쪽이든 그 시점의 (A, b*, T, t0, vr, 점수)를 **동결**해 신호 기록에 저장한다. 이후로 다시 맞추지 않는다.
9. 돌파가 아니고 `exp(ℓ(t))·(1 − TL_NEAR_PCT) ≤ C[t] ≤ exp(ℓ(t))` 이면 '돌파 임박'.

**동결된 선이 있을 때** (t > t0). 선 값은 `lv_t = exp(ℓ(t))` 로 동결된 A, b* 를 연장한 것이다.

10. **실패**: `C_t ≤ lv_t` 이면 실패다.
    - 아직 확인 전이면 '실패(가짜 돌파)'.
    - 확인 뒤면 '실패'. Bulkowski 의 첫 종가 이탈 매도가 둘째 종가를 기다리는 것보다 나았다.
    - 어느 쪽이든 동결을 풀고 처음부터 다시 탐색한다.
11. **안착 확인**: 확인 전이고 다음 중 하나면 '안착 확인' 이다. 이 단계가 화면의 '돌파' 이고 t_conf = t 다.
    - `C_t ≥ lv_t × (1 + TL_CONF_PCT)`
    - `t − t0 + 1 ≥ TL_CONF_BARS` (그동안 모든 종가가 선 위)
    - 돌파일 t0 자체도 (a) 조건으로 당일 확인될 수 있다. Murphy 의 3% 필터는 마감 즉시 적용된다.
12. **확인 뒤**
    - 선 쪽으로 되돌아오는 것(종가가 선 위에 있는 한)은 실패가 아니다. Bulkowski 표본에서 되돌림은 흔했다(§11).
    - '돌파' 표시는 `TL_DISPLAY_BARS` 동안 유지한다.

**점수** (가중치는 `구현 선택`. 기울기를 가장 크게 준다. Bulkowski 표본에서 기울기 효과가 약 10%p, 간격 · 길이 · 거래량 추세가 각각 약 2%p 였다.)
- 접점 수: 3 / 4 / 5 이상
- 간격 중앙값 13 초과
- 길이 48 초과
- 완만한 기울기
- 돌파 전 거래량 감소
- 진입 추세 평평
- 바닥 망치형 꼬리표
- 돌파 거래량 비율 vr

**바닥 망치형 꼬리표**: j ∈ [t0 − 20, t0 − 1] 중 `is_hammer(j)` 이고 '바닥권'(§4.3)인 봉이 있으면 날짜와 함께 표시한다.

**다시 그리지 않는다**
- LuxAlgo 'Trendlines with Breaks'(https://www.luxalgo.com/library/indicator/trendlines-with-breaks/)는 새 피벗이 생길 때마다 선을 다시 그리고, 기본 설정으로 과거까지 덧칠한다. 이것이 피해야 할 함정이다.
- 리포트 차트에는 신호 기록에 동결해 둔 선을 그대로 그린다.

---

## 5. `trendline_fib` — 빗각 돌파 + 피보나치 눌림

1. **전제**: `trendline_break` 에 동결된 선(A, b*, 접점 T, t0)이 있고, t_conf 에 '안착 확인' 이 됐다.
2. **파동 저점**: `L = min(Low[p_last..t0])`. p_last 는 T 의 마지막 접점이다.
   - 스펙의 '돌파 직전 저점' 이다.
   - Bulkowski 측정 규칙도 마지막 접점 뒤의 최저점을 쓴다.
3. **피보 상태 기계 시작**: §3.2 를 trigger b := t0 로 시작한다. 장대양봉 조건은 쓰지 않는다.
   - H 후보 = `max(High[t0..t])`.
   - `FIB_SWING_CONFIRM`, `FIB_H_MAX_BARS`, 라인, 접촉, 손절, 단계 규칙은 §3 과 같다.
4. **신호 시점**: SIGNAL 은 t ≥ t_conf 일 때만 낸다. 그 전에 접촉이나 반등이 있으면 기록만 해 둔다.
5. **추가 무효**: 동결된 추세선 아래에서 종가가 나오면(`trendline_break` '실패') 설정은 INVALID 다.
6. **두 규칙이 부딪칠 때**
   - 추세선 돌파 뒤에는 선 쪽으로 되돌아오는 일이 흔하다(Bulkowski).
   - 되돌림이 선까지 내려가면서 `lv(0.618)` 아래로 마감할 수 있다. 그러면 추세선은 살아 있어도 피보 설정은 무효다.
   - 두 상태를 같이 보인다.

---

## 6. `day_leader` — 10% 주도주 관찰 (일봉으로 되는 부분만)

| 상수 | 값 | 근거 | 등급 |
|---|---|---|---|
| `DL_BASIS` | `'open'` (스펙, 기본) / `'prev_close'`. 둘 다 계산해서 보인다: `up_open = C/O − 1`, `up_prev = C/C[−1] − 1`. | tilnote 영상 요약은 당일 10% 이상 오른 종목이라고만 하고 무엇 대비인지 밝히지 않는다. 시가 대비는 **미검증**이다. | L |
| `DL_MIN_CHG` | 0.10 | 영상. 구조적 이유: 정적 VI 는 직전 단일가 대비 ±10% 에서 발동하고 2분간 단일가 매매로 바뀐다 (키움 https://download.kiwoom.com/kiwoom_easy_help_new/5110.htm). 개장 직후의 직전 단일가가 시가라는 것은 추론이다. 전일 종가를 기준으로 쓰는 자료(kbthink)도 있어 **충돌**이 있다. | M |
| `DL_VOL_MULT`, `DL_VOL_N` | 3.0, 20 (당일 제외) | `구현 선택`. 블로그의 '세력봉 5~10배'(thecheck)는 L 등급이라 쓰지 않았다. 당일을 빼야 급증한 거래량이 제 기준선을 부풀리지 않는다. | — |
| 피보 참고가 | `lv(r) = H_t − r·(H_t − L_t)`, r = 0.236 · 0.382 · 0.5 (0.618 표시) | tilnote: 영상의 분봉 자동 지표는 인식한 저점 · 고점에 0.236 · 0.382 · 0.5 · 0.618 · 1 · 1.618 을 그린다. 진입은 38.2% 지지 반등 캔들. 분봉 크기는 요약에 없어서 스펙의 '3분봉' 은 미검증이다. | L–M |
| `DL_ORDER_AMBIG` | 0.3: `(O − L)/(H − L) > 0.3` 이면 '저가→고가 순서 불명' | `구현 선택`. 일봉으로는 저가와 고가 중 무엇이 먼저 났는지 알 수 없다. | — |

- **같은 생각의 권위 있는 출처** (분봉 영역이라 EOD 로 코딩할 수 없고 참고만 한다): Bulkowski Daytrade (https://thepatternsite.com/Daytrade.html).
  - 일직선 상승 뒤 38% 또는 50% 되돌림에서 반전을 기대한다.
  - 종목과 지수 10분 차트가 같은 방향으로 돌아설 때 들어간다.

**알고리즘** (EOD t)
1. `up_open`, `up_prev`, `vr = V_t / mean(V[t−20..t−1])` 를 계산한다.
2. **후보**: `C_t > O_t` 이고, `DL_BASIS` 쪽 등락 ≥ `DL_MIN_CHG` 이고, `vr ≥ DL_VOL_MULT`.
3. **표시** (t+1 하루 동안 유효, `구현 선택`)
   - `lv(r)`, `up_open`, `up_prev`, `vr`, 순서 불명 꼬리표.
   - 안내문: 'HTS 3분봉에서 반등 양봉 다음 봉 시가 진입 · 손절 기준선 이탈'.
4. 진입 판정은 하지 않는다(스펙 그대로).

---

## 7. `ma60_supply` — 60일선 수급 돌파

**이평선 이름 출처**
- 한국경제 생글생글 2005-10-31 (https://sgsg.hankyung.com/article/2005102520411) [H]
  - 중기 60일선은 매수 · 매도 수급이 좌우하므로 수급선이라 부른다.
  - 5일선 · 20일선은 재료선이라고 부른다.
- 머니투데이 2003-04-29 (https://www.mt.co.kr/stock/2003/04/29/2003042918362686531) · 2008-04-20 (https://www.mt.co.kr/stock/2008/04/20/2008042011120047780): 120일선 = 경기선. [H]
  - **충돌**: 한경 2005 는 120일 또는 200일선이라고 한다. 국내 HTS 관례인 120 을 유지한다.
- 머니투데이 2008-10-15 (https://www.mt.co.kr/stock/2008/10/15/2008101511101671229): 20일선 = 단기 생명선. [M]

**영상의 논리** (tilnote 요약): 바닥권의 단기 골든크로스는 반등에 그치는 경우가 많다. 진짜 추세 전환은 60일선 돌파에 기관 · 외국인 매수가 따라와야 한다.

**파라미터**

| 상수 | 값 | 근거 |
|---|---|---|
| `MA60_N` | SMA60 (종가, 오늘 포함). 이력 60봉 미만이면 건너뛴다. | §0.2 |
| 돌파 | `C[t−1] ≤ SMA60[t−1]` 이고 `C[t] > SMA60[t]` | 스펙, 키움 돌파 정의 |
| `MA60_FLOW_DAYS` | 5 | **출처 없음 — `구현 선택`**. 영상 요약에도, 한국 뉴스 · 위키독스 · 키움 도움말에도 일수 기준이 없다. 키움 0150 은 'N일 전' 조건을 사용자가 쌓는 방식이다. 5 = 1주(5거래일)이며 스펙과 같다. |

**수급 라벨** (Tech 투자자 자료 중 날짜 ≤ t 인 행만 쓴다. 투자자별 매매는 장 마감 뒤 확정된다.)
- 순매수 금액(원)을 우선 쓰고, 없으면 수량을 쓴다.
- `f_d = 기관_d + 외국인_d`, `s5 = Σ f[t−4..t]` 로 둔다.

| 라벨 | 조건 |
|---|---|
| '수급 동반' | `f_t > 0` 이고 `s5 > 0` (스펙) |
| '쌍끌이' (추가 꼬리표) | 기관 5일 합 > 0 이고 외국인 5일 합 > 0 |
| '수급 역행' | `s5 < 0` |
| '수급 약함' | 위에 해당하지 않는 나머지 (`구현 선택`) |
| '수급 미확인' | 5일 중 하루라도 자료가 없다. 지어내지 않는다. |

**함께 보일 것**: 20일선(생명선) 위 여부, 120일선(경기선) 위 여부.

---

## 8. 불코우스키 체크리스트 10 — 판정 규칙

**출처**: https://thepatternsite.com/tradehelp.html (Bulkowski's Trading Checklist). 항목 내용은 이번에 직접 다시 확인했다. 판정은 '통과 · 경고 · 모름' 중 하나다.

| # | 항목 | 판정 규칙 | 근거 | 등급 |
|---|---|---|---|---|
| 1 | 시장 추세 | `market.py` 그대로. 상승 확인 = 통과, 조정 · 하락 = 경고, 자료 없음 = 모름. | Bulkowski: 우세한 시장 추세 방향으로 매매한다(수치 없음). | H(항목) |
| 2 | 산업 위치 | `sector.py` 그대로 | Bulkowski: 같은 업종 종목들이 고점 · 바닥을 만드는 중인지, 누가 업종을 이끄는지 본다. | H(항목) |
| 3 | 주봉 = 일봉 | 완성 주봉 종가 > 10주 SMA 이고 일봉 `C > SMA50` 이면 통과. 하나라도 아니면 경고. 완성 주 10개 또는 일봉 50개 미만이면 모름. | Bulkowski: 한 단계 위 눈금(주봉)에서 위협적인 패턴 · 추세 · 지지저항 · 추세선을 본다. 이평은 말하지 않는다. → 이평 규칙은 `구현 선택` (10주 ≈ 50일). | H(항목) |
| 4 | 이 종목 과거 성취율 | 스펙 그대로: replay 로 20거래일 뒤 결과. 3건 미만이면 '표본 적음'. | Bulkowski: 같은 종목에서 다른 패턴을 찾아 어떻게 됐는지 본다. 20거래일 · 3건은 `구현 선택`. | H(항목) |
| 5 | 산업 상대강도 | 업종 RS = 구성 종목 `C[t]/C[t−126] − 1` 의 평균(126봉 미만 종목 제외). 업종 순위 백분위가 상위 `CK_IND_RS_TOP = 0.25` 안이면 통과, 그 밖은 경고. 업종 매핑이 없거나 구성 종목이 3개 미만이면 모름(`구현 선택`). | Bulkowski industryRS (https://thepatternsite.com/industryRS.html), 아래 별도 정리. ⅓ 은 옵션으로 둔다. | H |
| 6 | 상승 추세 확인 | `C > SMA20` 이고 `C > SMA60` 이면 통과 | Bulkowski: 가격이 위로 돌아설 때까지 기다린다(이평 없음). → `구현 선택` 유지. | H(항목) |
| 7 | 위 저항 | 아래 별도 정리 | Bulkowski 체크리스트, buylow.html | H(항목) / `구현 선택`(%) |
| 8 | 아래 지지 · 손절 | 아래 별도 정리 | https://thepatternsite.com/stops.html (22봉 평균 고저폭 × 2 를 최근 저가에서 뺀다. 배수는 예전엔 1.5 였다). 체크리스트: 손절은 현재 변동성의 2배보다 가깝게 두지 않는다. | H |
| 9 | 데드캣 | 아래 별도 정리 | 아래 별도 정리 | H |
| 10 | 연속 급등 | 아래 별도 정리 | 아래 별도 정리 | H(충돌) |

**5번 · 산업 상대강도 (Bulkowski 방식)**
- 업종마다 매일, 구성 종목들의 6개월 전 대비 평균 % 변화로 순위를 매긴다.
- 44업종을 1–11 / 12–22 / 23–33 / 34–44 위로 나눈다. 최상위 그룹은 대략 상위 ¼ 이다.
- 한 업종이 최상위 그룹에 머무는 기간은 평균 21~47일이다.
- 그의 매매 시험에서는 업종 순위가 14위 밖으로 밀리면 팔았다.

**7번 · 위 저항**
- R = 진입가(신호 종가)보다 높은 확정 소고점(k=3, p+3 ≤ t) 중 가장 낮은 가격이다. 범위는 최근 252봉(`CK_RES_LOOKBACK`).
- 그런 소고점이 없으면 `R = max(High[t−251..t−1])` 을 쓴다.
- `C_t ≥ max(High[t−251..t−1])` 이면 '위 저항 없음(신고가)' 으로 **통과**한다.
- 그 밖에는 거리 `d = R/entry − 1` 을 보인다. `d < CK_RES_WARN_PCT = 0.10` 이면 경고('먹을 폭 작음'), 아니면 통과. 기법 손절 거리 대비 d 의 비율도 함께 보인다.
- 근거
  - Bulkowski 체크리스트는 연중 고점 근처, 될 수 있으면 신고가로 돌파하는 패턴을 고르고 위 저항을 살피라고 한다. → 스펙의 '52주 고점 10% 이내 = 경고' 는 이 항목을 뒤집은 것이라 바꾼다.
  - **충돌**: 그의 buylow 통계는 연중 하단 ⅓ 을 더 낫게 본다(§11).
  - 10% 는 `구현 선택` 이다.

**8번 · 손절**
- 기법 손절 거리 `s = 1 − stop/entry` 를 보인다.
- 변동성 손절 `vstop = Low_t − CK_VSTOP_MULT(2.0) × mean(High − Low, t−21..t)` (`CK_VSTOP_N = 22`, 최근 봉 포함, EOD 에 확정된 값).
- `stop > vstop`, 즉 기법 손절이 변동성 손절보다 진입가에 가까우면 경고('손절이 변동성 2배보다 가까움'). 아니면 통과.

**9번 · 데드캣**
- **사건**: `C[j]/C[j−1] − 1 ≤ −CK_DCB_DROP(0.15)` (수정주가 기준, 기업행위일은 제외).
- **2015-06-15 이전 봉**: −0.145 이하(하한가 호가 단위 반올림을 감안)이거나 2일 누적 −15% 이하이면 사건으로 본다(`구현 선택`).
- **판정**
  - [t−125, t] 안에 사건이 있으면 경고 '데드캣(6개월)'.
  - [t−251, t−126] 에만 있으면 통과로 두되 '참고: 6~12개월 전 급락' 을 표시한다(영상의 6~12개월).
  - 이력이 126봉 미만이면 모름.
- **공시 위험**: 공시위험 JSON(작전주 꼴 · 감사 · 자본잠식 · 가속도 국면)이 있으면 경고 꼬리표를 덧붙인다(스펙 유지). 공시 자료가 없다는 것은 더 이상 '모름' 의 사유가 아니다.
- **근거**
  - https://www.thepatternsite.com/dcb.html: 사건 = 종가가 전일보다 15~70% 낮게 마감. 보통 갭 하락으로 온다.
  - 체크리스트: 최근 6개월 안에 데드캣 바운스가 있었던 종목은 피한다.
  - 《Encyclopedia of Chart Patterns》 2판 54장 (https://sacredtraders.com/dead-cat-bounce/ 재수록): 최소 15%.
  - **충돌**: 1999년 S&C 글은 25~70% 를 쓴다(검색 요약으로만 확인). 그의 데드캣 매수 셋업은 41~46% 를 쓴다(https://thepatternsite.com/DCBSetup.html).

**10번 · 연속 급등**
- `up_streak` = t 에서 끝나는 연속 `C > C[−1]` 일수.
- 스펙 조건(최근 5일 중 4일 이상 상승이고 `C_t/C_{t−5} − 1 ≥ CK_RUN5_PCT(0.20)`)이면 경고. 문구는 '단기 급등 — 되돌림 뒤 진입 고려' 로 하고 '추격 금지' 는 쓰지 않는다.
- 그 밖에 `up_streak ≥ CK_STREAK_WARN(4)` 이면 통과로 두고 '연속 상승 N일' 메모를 단다.
- **근거와 충돌**
  - Bulkowski 체크리스트: 여러 날 오른 뒤에는 매수 직후 반전을 예상하고, 돌아설 때를 기다린다.
  - https://www.thepatternsite.com/QConsecutive.html: 돌파 전에 3일 넘게 종가가 오르면 성과가 낫고, 되돌림이 적고, 상향 돌파 실패가 절반으로 준다.
  - 두 자료가 엇갈리므로 강한 금지를 두지 않는다. 4/5일과 +20% 는 `구현 선택` 이다.

**Bulkowski 의 추가 주의**: 장중에 너무 많이 오른 종목은 거르라고 한다(수치 없음, 정보 표시만).

---

## 9. 청산 계획 (표시만)

### 9.1 1차 — 5일선 종가 이탈
- **규칙**: `C_t < SMA5_t` (`EXIT_MA1 = 5`, 종가 기준).
- **근거** [L–M]
  - tilnote 영상 요약: 5일선 또는 10일선을 이탈하면 이익을 실현한다.
  - 다음 카페 Antsstory 2011-11-29 (https://m.cafe.daum.net/Antsstory/DJzh/152): 5일선 위 종가에 사고, 아래 종가에 판다.
  - 시사오늘 2010-04-06 전석 칼럼 (https://www.sisaon.co.kr/news/articleView.html?idxno=2026).
  - '종가 기준' 은 커뮤니티 출처에서 왔다.

### 9.2 2차 — 모랄레스 · 캐셔 10일선 위반

**이 문서의 유일한 원문 인용.** TradingView '7 Week Rule' 스크립트 설명(https://www.tradingview.com/script/kDC1dFjU-7-Week-Rule/)은 10일선 아래 종가 뒤에 오는 다음 움직임을 위반으로 정의한다: "a move on the next day below the intraday low of the first day".

- 이 문장은 책 원문이 아니다. 《Trade Like an O'Neil Disciple》 을 옮긴 2차 출처다.
- 책 원문은 접근하지 못했다(O'Reilly 미리보기 · Bookmate 403).

**구현용 규칙 문장** (`EXIT_MA_TYPE = 'SMA'`)

① **무장일 d**: `C_d < SMA10_d` 이고 `C_{d−1} ≥ SMA10_{d−1}` 인 날, 즉 10일선 아래로 마감한 첫날이다. **무장 자체는 위반이 아니다.**
   - 근거: 《In the Trading Cockpit with the O'Neil Disciples》 Everand 미리보기의 예시 설명 (https://www.everand.com/book/343295426). 이틀에 걸쳐 회복하면서 무장일 저가를 깨지 않은 종목은 위반으로 보지 않았다.

② **위반 시점** (`EXIT_10D_WINDOW`)
   - `'next_day'` (기본; 스펙 · TradingView · 2010년 책 인용 검색 요약): `Low_{d+1} < Low_d`.
   - `'until_reclaim'` (옵션; Everand 발췌 · Edgerater · Bulkowski 는 '그 뒤' 라고만 쓴다): d 뒤 종가가 SMA10 위로 돌아오기 전의 어느 봉이든 `Low_k < Low_d`.
   - 같은 값(=)은 위반이 아니다(엄격한 <).

③ **50일선 위반**: 같은 두 단계를 SMA50 에 적용한다 (https://in.tradingview.com/chart/VNINDEX/AgmKyPf9-Vnindex-Apr-2022-Rules-of-violation-of-the-50-day-MA [M], Bulkowski).

④ **7주 규칙** (`EXIT_7WK_BARS = 35`, `EXIT_7WK_MODE`). 출처마다 읽는 방식이 조금 다르다.
   - `'edgerater'` (기본): 매수 뒤 35거래일 안에 10일선 위반이 있었으면, 그 뒤로는 50일선 위반이 매도 기준이다. 없었으면 10일선이 기준이다.
     - Edgerater (https://edgerater.com/blog/morales-and-kacher-signals-template).
     - TradingView: 7주 넘게 10일선을 지킨 종목은 10일선 위반에 판다.
     - Morales · Kacher 칼럼(https://townhall.com/author/print/903240, 2011-10-15)은 수익 중인 포지션에서 50일선으로 바꾸라고 한다.
   - `'bulkowski'`: 보유 35거래일 미만이면 50일선 위반에 팔고, 35거래일 이상이면 10일선 위반에 판다 (https://thepatternsite.com/KacherMorales.html).
     - 그는 반도체 · 소매 · 원자재 업종에 50일선을 쓰는 예외도 적었다. 시가총액 50억 달러 초과 예외는 적었지만 시험에서는 쓰지 않았다.

⑤ **이평 종류**: SMA 다. Bulkowski 검증과 TradingView 기본값이 SMA 이고, 책 발췌는 종류를 밝히지 않는다. [M]

**화면 표시**
- 오늘의 SMA5 · SMA10 · SMA50 값.
- 오늘이 무장일이면 '내일 저가 {Low_t} 하회 시 10일선 위반(모랄레스)'.
- `'until_reclaim'` 이면 '기준 저가 {Low_d} ({d})'.
- 7주 안내: '모랄레스식으로는 신호 뒤 35거래일 동안 50일선({SMA50_t}) 위반이 기준'. 가정 진입은 신호 봉이다.

**재현 채점 체결가** (쓸 경우): 위반 봉 k 에서 `min(O_k, Low_d − 1호가)` (`구현 선택`).

**화면 주석** [불코우스키 미국 통계]
- Bulkowski 가 557종목, 2001-03-12 ~ 2010-10-01 일봉으로 이 규칙들을 시험했다.
- 더 낮은 저가를 기다리는 방식이, 종가 이탈 다음 날 바로 파는 방식보다 결과가 나빴다.
- 대략 3건 중 2건이 손실이라 권하지 않는다고 결론지었다. 다만 자기 시험이 저자들의 방식과 다를 수 있다고 본인이 밝혔다.

**보조 확인**: Bulkowski 매매 도움말
- 상승 추세선 아래 종가는 추세 변화의 이른 경고다.
- 62% 넘는 되돌림이면 판다.

**20일선**: 모랄레스 · 캐셔의 20일선 규칙은 찾지 못했다. 국내 관례에서 20일선은 '단기 생명선' 으로 이름만 쓴다. IBD 21일 EMA 는 지수용 Market School 도구로 보이는데, investors.com 이 막혀 확인하지 못했다.

---

## 10. 시장 맥락 칸

**지수 120일선**: KOSPI · KOSDAQ 의 C 와 SMA120(경기선) 비교.

**고점 대비 낙폭**: `dd = C_t / max(C since 마지막 확정 저점) − 1`. 장중 기준(`Low_t` / `max High`)도 같이 보인다.

**마지막 상승 파동 되돌림**
- **앵커**: 종가 ZigZag `MKT_ZZ_PCT = 0.20` 의 마지막 확정 저점 L.
  - 이 저점은 그 뒤 20% 이상 올라야 확정된다. 그때까지 마지막 다리는 잠정이다(ChartSchool ZigZag).
  - 20% 는 `구현 선택` 이다. 약세장 −20% 관례와 같은 크기로, 큰 파동만 잡는다.
- **H** = `max(High[L..t])` (t 까지의 누적 최고. 미래 자료 없음).
- `retr = (H − C_t)/(H − L)`.
  - 0.5 ≤ retr ≤ 0.618 이면 '50~61.8% 구간' 깃발.
  - retr > 0.618 이면 '61.8% 넘음'.
- 확률이나 반등 기대치는 쓰지 않는다.

**근거**
- ChartSchool Dow Theory: 이차 조정은 앞선 움직임의 ⅓~⅔ 를 되돌리고 흔히 50% 다(Hamilton 인용). [H]
- 김종봉 50% 주장은 공개 자료(《돈의 시나리오》 리디 https://ridibooks.com/books/4803000120 · 교보 소개)에서 확인하지 못했다.
  - 그래서 '영상에 따르면 김종봉은 50% 를 강조' 라고만 적는다.
  - tilnote 요약의 '지수가 절반 이상 하락하면 매수 타이밍' 이라는 표현은, 50% 하락인지 50% 되돌림인지 모호하다.

**사례** (검증용 사실일 뿐 예측이 아니다. n=2. 수치는 topicB 노트의 출처에서 왔다.)

| 사례 | 기준 | 저점 → 고점 | 50% | 61.8% | 이후 저점 | 되돌림 |
|---|---|---|---|---|---|---|
| 2020–2022 | 장중 | 1439.43 (2020-03-19) → 3316.08 (2021-06-25) | 2377.76 | 2156.31 | 2134.77 (2022-09-30) | 62.95% |
| 2020–2022 | 종가 | 1457.64 → 3305.21 (2021-07-06) | 2381.43 | 2163.41 | 2155.49 | 62.23% |
| 2025–2026 | 장중 | 2284.72 (2025-04-09) → 9385.59 (2026-06-19) | 5835.15 | 4997.25 | 5262.77 (2026-07-29) | 58.06% |
| 2025–2026 | 종가 | 2293.70 → 9114.55 (2026-06-22) | 5704.12 | 4899.26 | 5593.56 (2026-07-30) | 51.62% |

- **2022 년 사례**: 저점이 61.8% 선을 아주 조금 넘었다(종가 기준 0.37%, 장중 기준 1.0% 아래).
  - 종가가 선 아래면 무효로 보는 엄격한 규칙이라면 '무효' 였을 것이다. ±1.5% 밴드라면 '지지' 였다.
  - 그 뒤 2022-11-11 까지 약 2483 으로 +15% 반등했다.
- **2026 년 사례**
  - 7-29 에 이틀 연속 서킷브레이커가 발동했다.
  - 8-18 고가 7216.62 까지 반등했다.
  - 2026-10-13 종가 6035.35 의 되돌림은 종가 기준 45.1%, 장중 저가 5911.11 은 장중 기준 48.9% 다.
- **로컬 캐시 범위**: `Tech/cache/ohlcv/KOSPI.pkl` 은 2023-08-24 ~ 2026-10-13 만 담고 있어서 2020–22 사례는 검증할 수 없다.

**지수 월봉 적삼병**: §2.3 그대로 적용한다.

---

## 11. 불코우스키 · 학술 통계 (맥락 전용)

- 이 절의 수치는 **Bulkowski 의 미국 주식 표본**(주로 강세장, 주가 $5 이상, 일봉)이다. **우리 데이터가 아니다.**
- 화면에는 접히는 '참고 — 불코우스키 미국 통계(우리 데이터 아님)' 줄에만 쓸 수 있다. 후보 옆에 확률처럼 쓰지 않는다.
- 스펙의 '사례 수익률을 화면에 쓰지 않는다' 원칙을 이 수치에도 똑같이 적용한다. 우리 성적은 체크리스트 4번과 기록 채점으로 잰다.

| 주제 | 그의 수치 | 표본 | URL |
|---|---|---|---|
| 적삼병 | 상승 반전 82%, 성과 순위 103개 중 32위, 빈도 순위 67위. 3,333건 중 하향 이탈 593건. 6% 상승을 '선물' 이라 부를 만큼 평균 움직임은 작다. | 미국 일봉 (S&C 2011: 500종목 10년) | https://thepatternsite.com/ThreeWhiteSoldiers.html |
| 망치형 | 상승 반전 60% (본인도 무작위에 가깝다고 평가), 순위 65위 | 같음 | https://thepatternsite.com/Hammer.html |
| 롱 화이트 데이 | 지속 58%, 순위 53위 | 같음 | https://thepatternsite.com/LongWhiteDay.html |
| 상승 장악형 | 반전 약 63% | 같음 | https://thepatternsite.com/BullEngulfing.html |
| 하향 추세선 돌파 | 평균 상승 51%, 중앙값 30%. 실패율(상승폭 미달): 5% 13%, 10% 24%, 20% 39%, 30% 50%. 되돌림 59%(약 14일에 완료), 되돌림 뒤 상승 81%. 선 시작 가격 도달 77%. 완만 56% vs 가파름 46%. 간격 넓음 52% vs 좁음 50%. 길이 김 52% vs 짧음 50%. 거래량 감소 52% vs 증가 50%. | 3,274선, 645종목, 1991-02 ~ 2021-04, 강세장 | https://thepatternsite.com/trenddown.html |
| 상향 추세선 매매 시험 | 평균 +0.7%, 중앙값 −0.9%, 승률 37%. 3접점 −2.1%, 4접점 +2%, 7접점 +7.5%(23건). 길이 44일 초과 +2.9% vs 이하 −1.4%. 첫 종가 이탈 매도(중앙 손실 0.9%)가 둘째 종가를 기다리는 것(1.3%)보다 나았다. | 3,720선, 699종목 | https://thepatternsite.com/uptrendlines.html |
| 피보 되돌림 | 손으로 고른 표본 중앙값 59%, 약 45% 가 61% 보다 깊음. 자동 시험에서 38 · 50 · 62 는 특별하지 않았다. | 489종목, 2009–2020 | https://thepatternsite.com/fib.html , https://thepatternsite.com/SwingSetup.html |
| 돌파 거래량 | 상향 돌파 평균 상승: 대량 37.6% vs 소량 35.8%. 되돌림 57% vs 18%. 대량이면 실패가 더 많다. | 약 8,000건 (사각형 · 쌍봉/쌍바닥; 추세선 아님) | https://www.thepatternsite.com/VolumeStudy.html |
| 연중 위치 | 상향 돌파 평균 상승: 하단 ⅓ 38%(1,421건), 중간 35%(1,874), 상단 ⅓ 36%(2,715). 10% 미달 실패: 12% / 16% / 16%. | 강세장 | https://thepatternsite.com/buylow.html |
| 데드캣 | 평균 하락 31%. 다음 날 더 낮은 저가 46%. 추세 저점은 약 7일 뒤. 3개월 안 두 번째 데드캣 26%, 6개월 안 38%. | — | https://www.thepatternsite.com/dcb.html |
| 연속 상승 | 돌파 전 3일 넘게 종가가 오르면 성과가 낫고 되돌림이 적으며, 상향 돌파 실패가 절반 | — | https://www.thepatternsite.com/QConsecutive.html |
| Kacher–Morales 규칙 | 평균 이익 1.2~3.1%, 이긴 거래 28~32%, 평균 낙폭(drawdown) 5.5~8.9%, 보유 29~43일. 권하지 않음. | 557종목, 2001-03-12 ~ 2010-10-01, 변형 16개 | https://thepatternsite.com/KacherMorales.html |

**학술 연구**
- Marshall · Young · Rose (Journal of Banking & Finance 30(8), 2006, https://ideas.repec.org/a/eee/jbfina/v30y2006i8p2303-2323.html): DJIA 종목 1992–2002 에서 캔들 기법으로 시장을 이긴다는 증거가 없었다.
- Tsinaslanidis 외 (2022): §3.0.
- KOSPI 를 대상으로 적삼병 · 망치형을 검증한 학술 연구는 찾지 못했다.

---

## 12. 출처가 엇갈리는 곳 → Config 플래그

| 주제 | 갈래 | 플래그 (기본) |
|---|---|---|
| 적삼병 최소 정의 | 양봉 3개(한경) vs 종가 상승까지(대다수) | `RTM_REQUIRE_HIGHER_CLOSE` (True) |
| 적삼병 맥락 | 바닥 · 횡보 뒤(키움 · Nison · 한경) vs 연중 고점 근처에서도 작동(Bulkowski 통계) | 바닥권은 필수, `RTM_YEARLY_POS` 는 표시 |
| 장대양봉 측정 | 전일 대비 %(한국 관례) vs 몸통 배수(Bulkowski · HTS) | 둘 다 AND. `LB_BODY_REL_K` 3.0, 완화 시 2.0/22 |
| 스윙 고점 확정 | 1봉(영상) vs 좌우 2봉(fractal) vs 2~20봉(Bulkowski) | `FIB_SWING_CONFIRM` ('video') |
| 피보 진입 깊이 | 23.6~50(영상) vs 깊은 되돌림이 낫다(Bulkowski 45~75%) | 매수 라인 고정, 61.8 무효 |
| 피보 손절 | 다음 라인 · 스윙 저점 · 저점 −5% · 7~8% · 5/10일선 | 1차 = 다음 라인, 나머지는 표시 |
| 거래량 기준선 | 5일(영상 · 키움) · 20 · 30(Bulkowski) · 50일(O'Neil) | 기법별 상수 |
| 5일 거래량 돌파 | 상향돌파(cross) vs 수준 비교 | `FIB_VOL_TEST` ('cross') |
| 소고점 창 | ±2(Bulkowski 정의) vs 3봉 대기(그의 소프트웨어 · LMW) | `TL_PIVOT_K` (3) |
| 추세선 앵커 | 최고점(Sperandeo) vs 거래량 봉(영상) vs 둘째 고점(AAII) | `TL_ANCHOR_MODE` ('highest') |
| 관통 허용 | 엄격(Bulkowski · 김정환) vs 관대(ChartSchool · AAII) | `TL_TOL_CUT` (0.005) |
| 돌파 확인 | 3%(Murphy · E&M) · 1~2%(단기 · Brandt) · 2종가(Murphy) · 3봉(Penteado) · 3~4일(영상) | `TL_CONF_PCT` 0.03, `TL_CONF_BARS` 3 |
| 돌파 거래량 | 필수(E&M · O'Neil · 영상) vs 되돌림 · 실패 증가(Bulkowski) | 필수 + `TL_SHOW_LOWVOL_BREAK` |
| 체크 7 | 연중 고점 근처 선호(체크리스트) vs 연중 저점이 낫다(buylow) | 위 저항 거리로 판정 |
| 체크 9 문턱 | 15%(사이트 · 백과 2판) vs 25%(1999) vs 41~46%(매수 셋업). 6개월 vs 6~12개월(영상) | `CK_DCB_DROP` 0.15, `CK_DCB_WINDOW` 126, 참고 252 |
| 체크 10 | 연속 상승 뒤 반전 경계(체크리스트) vs 3일 넘는 상승이 돌파에 유리(QConsecutive) | 경고 문구 완화 |
| 10일선 위반 시점 | 다음 날(TradingView · 2010 책 인용) vs 그 뒤 어느 날(Cockpit · Edgerater · Bulkowski) | `EXIT_10D_WINDOW` ('next_day') |
| 7주 규칙 해석 | Edgerater/TradingView vs Bulkowski | `EXIT_7WK_MODE` ('edgerater') |
| 경기선 | 120일(머니투데이) vs 120 또는 200일(한경 2005) | 120 |
| 정적 VI 기준 | 직전 단일가(키움) vs 전일 종가(kbthink) | 표시만 |
| 10% 기준 | 시가 대비(스펙) vs 전일 대비 — 영상 요약은 밝히지 않음 | `DL_BASIS` ('open'), 둘 다 표시 |

**출처 없이 남은 `구현 선택` 값** (전부 Config 상수)
- 적삼병: `RTM_MAX_LAG` 6, `RTM_LOW_MONTH_AS_FIRST`, 거래정지 행 제거, 미완성 월 판정 방식
- 장대양봉: `LB_VOL_MULT` 2 / 20, `LB_MIN_CHG` (블로그 근거뿐)
- 피보: `FIB_H_MAX_BARS` 20, `FIB_L_LOOKBACK` 60, `FIB_TOL` 1.5%, `FIB_TOUCH_MODE`, `FIB_REQUIRE_UP_CLOSE`, `FIB_APPROACH_PCT` 3%, `FIB_SETUP_EXPIRY` 30
- 추세선
  - `TL_LOOKBACK` 250, `TL_ANCHOR_VOL_MULT` 2, `TL_TOL_CUT` 0.5%, `TL_TOL_TOUCH_BELOW` 1.5% (유추)
  - `TL_MIN_GAP` 10, `TL_MIN_LEN` 40, `TL_NEAR_PCT` 2%, `TL_HAMMER_WINDOW` 20, `TL_DISPLAY_BARS` 20
  - 기울기 중앙값 창 250, 진입 추세 20봉, 점수 가중치
- 망치형: `HM_RANGE_REL` 1.0, 도지 처리
- 10% 주도주: `DL_VOL_MULT` 3, `DL_ORDER_AMBIG` 0.3
- 60일선 수급: `MA60_FLOW_DAYS` 5, '수급 약함' 라벨
- 체크리스트
  - 3번 · 6번의 이평 규칙
  - 4번의 20거래일 · 3건
  - `CK_RES_WARN_PCT` 10%
  - 9번의 2015 년 이전 처리
  - 10번의 4/5일 · 20%
  - 5번의 구성 3종목 하한
- 기타: 재현 채점 체결가, `MKT_ZZ_PCT` 20%

---

## 13. 추가할 테스트 (스펙 §테스트에 덧붙임)

### 공통
- 앞부분 불변: 무작위 봉을 덧붙여도 앞선 판정이 바뀌지 않는다. 기법마다 적용한다.
- 모든 비율 기준선이 당일을 빼는지 확인한다. 예: 평범한 49일 + 거대 거래량 1일.

### 적삼병
- 진행 중 달은 무시한다. 월말 마지막 거래일 EOD 에도 그 달은 미완성이다.
- 4번째 연속 양봉 달은 새 신호가 아니다.
- 저점 월이 양봉이어도 첫 병정이 아니다(기본 설정).
- 저점 앞 12개월 이력이 부족하면 신호가 없다.
- 거래정지 행이 월 시가 · 저가를 바꾸는 경우를 넣는다.
- 월 경계 갭 하락으로 종가 상승 조건만 떨어지는 경우를 넣는다.
- 키움 0봉전과 1봉전의 차이를 재현한다.

### 피보
- 고점 확정에 미래 봉이 필요한 경우.
- 확정 뒤 신고가가 나면 다시 CANDIDATE 가 된다.
- 접촉 경계: 정확히 lv × 1.015, 종가가 lv 보다 0.01% 아래.
- `wick` 과 `band` 차이: 2% 꼬리 관통 뒤 회복.
- MA5V 의 오늘 포함 · 제외 경계.
- `cross` 와 `level` 차이: 접촉일 거래량이 컸던 경우.
- 신호 창 4봉째는 거부한다.
- 갭 하락 손절 체결가.
- +7% 갭 상승에 몸통이 작은 봉은 장대양봉이 아니다.
- `since_swing_high` 와 `min_lookback` 에서 L 이 다른 경우.

### 추세선
- 소고점 지연: 오른쪽에 낮은 봉이 2개뿐인 고점은 p+3 전에는 접점이 아니다.
- 그 전에 선 위 종가가 있었으면 후보가 무효다.
- 장중 관통만 있으면 돌파가 아니다.
- 접점 2개는 거부, 3개는 통과, 5개는 가점.
- 접점 간격 9봉이면 그 접점은 거부한다.
- **확인 측정 회귀 사례**
  - 돌파 종가가 선 +2%, 다음 종가가 그날 선 +3.1% 면 둘째 날 '안착 확인' 이다.
  - 스펙의 '돌파일 종가 +3%' 방식이었다면 확인되지 않는다.
- 돌파일 종가 ≥ 선 × 1.03 이면 당일 확인된다.
- 확인 뒤 선 위 0.5% 까지 내려와도 유지되고, 선 아래 종가면 '실패' 다.
- 동결 뒤 더 높은 새 피벗이 생겨도 선은 그대로다.
- 거래량 미달 돌파는 '돌파(거래량 미달)' 단계가 된다.

### 망치형
- 몸통 0 (doji-hammer).
- 위꼬리가 정확히 0.1 × 평균 범위.
- 범위가 평균보다 작은 봉은 거부한다.
- 확인은 3봉 안에서만.

### 체크리스트
- 데드캣: −15.0% 정확히는 사건, −14.9% 는 아니다. 2015-06-15 전후. 126봉 경계.
- 신고가면 '위 저항 없음'.
- 변동성 손절보다 가까운 손절이면 경고.
- 업종 구성이 부족하면 모름.
- 진행 중 주봉은 제외한다.
- 연속 상승 4일은 메모만 남긴다.

### 청산
- 무장일 다음 날 저가가 같으면(=) 위반이 아니다.
- `until_reclaim` 은 사흘째 저가를 깬 경우를 잡는다.
- 35거래일 경계.
- 두 `EXIT_7WK_MODE` 차이.

### 10% 주도주
- 시가 대비와 전일 대비가 서로 다른 경우: 예를 들어 갭 +8% 뒤 시가 대비 +3%, 또는 갭 −5% 뒤 시가 대비 +11%.

### 60일선
- 전일 종가가 SMA60 과 같으면(≤) 돌파로 인정한다.
- 수급 5일 중 하루라도 빠지면 '수급 미확인'.

---

## 14. 출처 목록과 확인하지 못한 것

### 1차 · 주요 출처

**Bulkowski — thepatternsite.com**
- 캔들: ThreeWhiteSoldiers · Hammer · LongWhiteDay · TallCandleSAR · TallCandleSetup · MinorHiLow · BullEngulfing
- 추세선 · 스윙: trenddown · uptrendlines · QTL · QUTL · minorhl · 123tc
- 피보 · 되돌림: fib · SwingSetup · pullbacks
- 거래량: volbkout · Volume · VolumeStudy
- 매매 · 통계: glossary · buylow · tradehelp · stops · industryRS · QConsecutive · dcb · DCBSetup · KacherMorales · Daytrade
- **이번에 다시 확인한 페이지**: KacherMorales, dcb, stops, tradehelp, QConsecutive, buylow

**Bulkowski — Stocks & Commodities 2011 (Fidelity 재게재)**
- https://fidelity.com/bin-public/060_www_fidelity_com/documents/Top10CandlesWork_620095.pdf
- https://www.fidelity.com/bin-public/060_www_fidelity_com/documents/EightBestCandles.pdf

**코드**
- TA-Lib C 소스: https://github.com/TA-Lib/ta-lib (`ta_CDL3WHITESOLDIERS.c`, `ta_CDLHAMMER.c`, `ta_CDLLONGLINE.c`, `ta_global.c`, `ta_utility.h`)

**StockCharts ChartSchool**
- Fibonacci Retracements, ZigZag, Dow Theory, Trend Lines, Murphy 10 Laws, Candlestick Bullish Reversal Patterns
- StockCharts mailbag 2009 (피보 도구)

**키움**
- 조건검색 도움말 PDF: https://download.kiwoom.com/hero4_help_doc/KiwoomHero4_AdvancedSearch.pdf
  - 로컬 텍스트 `kiwoom.txt` 33행(돌파 정의), 482행(거래량 이평 골든크로스 예시)
- 도움말 1337 (시간외 종가): https://download.kiwoom.com/hero4_help_new/1337.htm
- 도움말 5110 (정적 VI): https://download.kiwoom.com/kiwoom_easy_help_new/5110.htm

**국내 증권사 · 사전**
- 한경 경제용어사전: seq=5747 (적삼병), seq=10062 (망치형)
- 미래에셋 HTS 0544
- 삼성증권 POP 1512

**논문**
- Lo · Mamaysky · Wang (NBER w7613)
- Penteado (arXiv 1302.1228)
- Tsinaslanidis 외 (doi 10.1016/j.eswa.2021.115893)
- Marshall · Young · Rose (2006)
- PMC8752186

**기타 영어권 출처**
- Peter Brandt (?p=12076)
- TigerShark 2007
- AAII (Weiss 2017)
- BabyPips (placing stops with fibs)
- MetaTrader 5 fractals
- CSI Data (월봉 구조)
- Motley Fool (약세장 정의)
- marketcalls (EWI 튜토리얼 재게재)
- tradingqna (MarketSmith India)
- LuxAlgo (O'Neil base · Trendlines with Breaks)
- Pineify (`ta.pivothigh`)

**모랄레스 · 캐셔 관련 2차 출처**
- TradingView 7-Week Rule
- Edgerater
- Everand 《In the Trading Cockpit》
- townhall 칼럼
- whatheheckaboom 2014 서평
- TradingView VNINDEX 50일선 글

**국내 언론 · 커뮤니티 · 일본 자료**
- 한국경제 생글생글 2005
- 머니투데이 2003 · 2008 (두 건)
- 이투데이 2015
- tilnote 영상 요약
- 다음 카페 Antsstory, 시사오늘
- i-whale, jungbosum
- 野村, iFinance, sevendata (赤三兵)

**KOSPI 사례 수치**: blockmedia 260213 · 886879, mt.co.kr, ajunews, asiae, brunch, newdaily, kbmaeil, bullstory, stock.pstatic.net 한화 리포트, 로컬 KIS 캐시

### 접근하지 못했거나 검증하지 못한 것 (출처로 내세우지 않는다)
- **Nison 원서**: 1library 403. 2차 전사본만 봤다.
- **Investopedia, investors.com (IBD)**: 크롤러가 막혀 있다.
- **김정환 《차트의 기술》**
  - 목차와 교보 미리보기만 봤다.
  - 영상의 9일<9주<9개월, 접점 3 vs 8, 3~4일 · 3~4%, 월봉 적삼병 규칙을 책에서 확인하지 못했다. **영상에서만 나온 주장**으로 다룬다.
- **Murphy 원서**: 3% 필터와 2일 규칙의 정확한 문장을 확인하지 못했다. Penteado 인용과 TigerShark · BabyPips 의 요약으로만 봤다.
- **《Trade Like an O'Neil Disciple》 원문**: O'Reilly · Bookmate 403. 위반 정의는 2차 출처로만 확인했다.
- **Bulkowski 《Trading Classic Chart Patterns》 (2002) 추세선 표**: 접점 4개 초과 48% vs 이하 35%, 간격 중앙 29일. 제3자 사본의 검색 요약으로만 봤으므로 책으로 확인하기 전에는 인용하지 않는다.
- **Bulkowski S&C 2002 'The Truth About Trendlines', 1999 데드캣 글**: 차단돼 있었다.
- **김종봉 《돈의 시나리오》 의 50% 주장**: 공개 소개문에는 없다.
- **ScienceDirect 원문** (Tsinaslanidis): 구역 폭 정의를 확인하지 못했다.
- **영상 원본 전사**: 얻지 못했다. tilnote 요약과 스펙의 타임스탬프 요약에 의존했다.
- **기관 · 외국인 순매수 일수 기준, 장대양봉 거래량 ×2, 피보 접촉 허용치, 추세선 접점 허용치 · 최소 간격 · 최소 길이**: 어느 출처에서도 숫자를 찾지 못했다. 모두 `구현 선택` 이다.
