# `time_warp` 定位誤差修正（2026-10-14）

相關追蹤：[pytimestretch issue #12](https://github.com/openmirlab/pytimestretch/issues/12)。

## 問題與結果

在 44.1 kHz、10 秒的測試音訊中，以 `(0,0) → (4,4) → (5,8) → (10,13)` 的秒數對應標記，把第 4–5 秒局部放慢四倍。舊版 `time_warp` 預設使用 Rubber Band：變速區內的 click 約提前 154 ms，區域後約延遲 57 ms。Signalsmith 的相同呼叫在變速區外也約延遲 14 ms。

現在未指定 `backend` 的 `time_warp` 改用 Bungee Basic，沿用原本的 `(來源影格, 輸出影格)` 標記格式。此測試的最大 click 定位誤差為 1.5 ms，輸出長度仍精確等於最後一個標記的輸出影格。`backend="bungee"` 可明確選擇同一路徑。`time_stretch` 與 `pitch_shift` 的預設引擎沒有改變。

## 改動

- `time_warp` 驗證標記和選項後，把標記欄位轉成 `time_scrub` 使用的 `(輸出影格, 來源影格)`，交由 Bungee Basic 渲染。呼叫端不必自行交換欄位。
- Signalsmith 的多標記變速路徑改用第一段的局部播放速率設定 pre-roll；等比例標記仍維持與 `time_stretch` 相同的處理方式。上述四倍局部變速測試中，變速區外的約 14 ms 延遲降至 0.4 ms 以內。
- 保留 `backend="rubberband"` 和 `backend="signalsmith"`，供需要其聲音特性、較廣輸入範圍、formant preservation 或 `quality="balanced"` 的呼叫端使用。
- 加入局部二倍／四倍變速、比率轉折附近的 click 定位，以及後端選項限制的回歸測試；同步更新 README、CHANGELOG 和套件指南。

## 使用方式與限制

```python
import pytimestretch as pts

warped = pts.time_warp(
    audio,
    44_100,
    markers=[(0, 0), (4 * 44_100, 4 * 44_100),
             (5 * 44_100, 8 * 44_100), (len(audio), 13 * 44_100)],
)
```

預設 Bungee 路徑支援單聲道或雙聲道、8–192 kHz、±24 半音。它不支援 `formants="preserve"` 或 `quality="balanced"`；指定這些選項會得到 `UnsupportedOptionError`。Bungee 的顆粒式處理可能改變密集瞬態的音色，因此定位精度與聽感應分別評估。

## 後續修正：明確指定的後端

同日的後續實驗找到 Signalsmith 的主要原因：引擎以分析視窗讀取較早的來源位置，變速後的 click 偏移約為「新倍率與第一段倍率之差 × 輸入分析延遲」。內部把變速標記沿來源軸後移 `inputLatency()`，沿輸出軸後移第一段對應的影格數，並補靜音尾段後裁回原本輸出長度。原始四倍案例區內約晚 175 ms 的 click 降至約 5 ms 內；在 22.05、44.1、48、96 kHz 的 high／balanced 合成 click 測試中，最大約 1.4 ms。等比例標記保留原本的渲染路徑。

Rubber Band R3 每次 `process()` 才檢查 keyframe。把有標記的 warp 輸入區塊從 4096 縮為 256 影格後，原始案例的區內誤差從約提前 154 ms 降到約提前 32 ms，區後從約延遲 57 ms 變成約提前 13 ms；一般 `time_stretch` 仍用 4096 影格。縮到 64 影格沒有進一步改善區內誤差。直接平移 keyframe 會使結果跳到不同的偏移，不能當成穩定校正。單純按標記分段渲染雖改善 click 位置，接縫卻會產生波形跳變、音量凹陷或瞬態衰減，因此沒有採用。

再針對 R3 的剩餘誤差做了可還原的實驗，均未達到可合併的精度：改用 R2 雖改善局部四倍案例，卻讓部分等比例標記與區外 click 誤差增加到約 13 ms，並使原有 Rubber Band 測試有 8 項失敗；`quality="balanced"` 在 44.1 kHz 可把四倍案例的區內誤差降到約 7 ms，但在 48 kHz 約 20 ms、96 kHz 約 23 ms，沒有跨取樣率的穩定優勢。固定平移內部標記也會隨訊號內容而變：同一平移量在孤立脈衝與低雜訊上的 click 誤差可相差逾 20 ms。

R3 到達原始四倍案例的 4 s 標記時，內部已消耗 176640 個輸入影格，累計輸出 174592 個影格；到達 5 s 標記時，分別為 220544 和 350208，兩次都沒有正好落在標記的輸入／輸出位置。實驗性地按當下內部時鐘重新計算下一段倍率後，四倍案例反而變成區內約晚 29 ms、區後約晚 50–60 ms，其他標記配置也退步。這表示單用累計影格數不能推回瞬態的實際合成位置；目前沒有證據支持以 binding 端的固定偏移或倍率修正來保證 R3 對齊。上述 R2、R3 實驗改動均已還原。

Issue #12 仍追蹤 Rubber Band 的剩餘誤差，以及密集瞬態等素材上的定位與音質限制；這些測量不是所有素材的精度保證。

[獨立 C++ 重現程式](repros/issue12-rubberband-r3/README.md)直接連結專案釘選的 Rubber Band v4.0.0 原始碼，不經過 Python binding，仍量到相同案例區內約提前 32 ms、區後約提前 13 ms。這證實剩餘偏移不只出現在 pytimestretch 的包裝路徑。

## 驗證範圍

- 專案完整測試：401 passed、2 deselected；`ruff check .` 通過。
- `uv build` 通過；從建出的 wheel 安裝後，在原始 44.1 kHz 重現案例中量得最大誤差 1.5 ms。
- 額外測試涵蓋 22.05、44.1、48、96 kHz 及局部二、四、八倍變速，最大誤差 4.35 ms；在 4 s／5 s 標記前後 10 ms 的測試，最大誤差 2.31 ms。這些是合成 click 測量，並非對所有素材保證的誤差上限。
- 後續修正另以相同重現音訊、獨立的邊界 click、跨採樣率測試和各引擎的回歸測試驗證；從 source distribution 建出的 wheel 安裝到 repo 外後，也重現了上述兩個後端的改善。
