"""推移グラフ(インライン SVG)の座標計算のユニットテスト。"""

from enop_finance import chart


def test_empty_chart_has_no_bars():
    c = chart.bar_chart([])
    assert c.bars == []
    assert not c.has_data


def test_bars_are_positioned_inside_the_plot_area():
    c = chart.bar_chart([("01", 100_000), ("02", 200_000)], width=400, height=200)
    assert c.view_box == "0 0 400 200"
    assert len(c.bars) == 2
    for bar in c.bars:
        assert c.plot_left <= bar.x
        assert bar.x + bar.width <= c.plot_right
        assert bar.y >= 0
        assert bar.height > 0
    # 値が大きい月ほど棒が高い
    assert c.bars[1].height > c.bars[0].height


def test_bar_width_is_capped():
    c = chart.bar_chart([("01", 100_000)], width=800)
    assert c.bars[0].width == chart.MAX_BAR_WIDTH


def test_negative_values_hang_below_the_baseline():
    c = chart.bar_chart([("01", 200_000), ("02", -100_000)])
    positive, negative = c.bars
    assert not positive.negative
    assert negative.negative
    assert positive.y + positive.height == c.baseline_y
    assert negative.y == c.baseline_y


def test_reference_line_is_placed_for_the_target():
    c = chart.bar_chart([("01", 2_000_000)], reference=3_000_000, reference_label="目標")
    assert c.reference_y is not None
    assert c.reference_label == "目標"
    # 目標(未達)は棒より上にある = Y 座標が小さい
    assert c.reference_y < c.bars[0].y


def test_reference_line_outside_the_scale_is_dropped():
    c = chart.bar_chart([("01", 100)], reference=-5_000_000)
    assert c.reference_y is None


def test_radius_never_exceeds_half_the_bar():
    c = chart.bar_chart([("01", 1)], width=200)
    assert c.bars[0].radius <= c.bars[0].width / 2


def test_format_compact():
    assert chart.format_compact(0) == "HK$0"
    assert chart.format_compact(50_000) == "HK$500"
    assert chart.format_compact(24_000_000) == "HK$240k"
    assert chart.format_compact(150_000_000) == "HK$1.5M"
    assert chart.format_compact(-500_000) == "-HK$5k"
