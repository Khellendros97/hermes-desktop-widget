from hermes_panel.panel import _normalize_notification_text


def test_normalize_notification_text_flattens_newlines():
    assert _normalize_notification_text("第一行\n第二行\n第三行") == "第一行 第二行 第三行"


def test_normalize_notification_text_collapses_extra_whitespace():
    assert _normalize_notification_text("  a\t\tb   \n  c  ") == "a b c"
