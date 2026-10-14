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

預設 Bungee 路徑支援單聲道或雙聲道、8–192 kHz、±24 半音。它不支援 `formants="preserve"` 或 `quality="balanced"`；指定這些選項會得到 `UnsupportedOptionError`。Bungee 的顆粒式處理可能改變密集瞬態的音色，因此定位精度與聽感應分別評估。明確指定 Rubber Band 或 Signalsmith 時，突變速區內的 click 仍可能明顯偏離標記；issue #12 會繼續追蹤，這次變更不宣稱修好了兩個引擎的所有定位問題。

## 驗證範圍

- 專案完整測試：379 passed、2 deselected；`ruff check .` 通過。
- `uv build` 通過；從建出的 wheel 安裝後，在原始 44.1 kHz 重現案例中量得最大誤差 1.5 ms。
- 額外測試涵蓋 22.05、44.1、48、96 kHz 及局部二、四、八倍變速，最大誤差 4.35 ms；在 4 s／5 s 標記前後 10 ms 的測試，最大誤差 2.31 ms。這些是合成 click 測量，並非對所有素材保證的誤差上限。
