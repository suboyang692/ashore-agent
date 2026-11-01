"""模型自检不泄露密钥，并能识别常见的账户/额度错误。"""
from app.inspect_llm import _billing_hint, mask_key


def test_mask_key_never_returns_the_full_secret():
    secret = "sk-abcdefghijklmnopqrstuvwxyz"
    masked = mask_key(secret)

    assert secret not in masked
    assert masked.startswith("sk-abc")


def test_billing_hint_explains_arrearage():
    hint = _billing_hint(RuntimeError(
        "Error code: 400 - {'code': 'Arrearage', 'message': 'overdue-payment'}"
    ))

    assert hint and "欠费" in hint
