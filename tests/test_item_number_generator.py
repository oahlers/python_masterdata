import pytest

from app.item_number_generator import generate_item_number


def test_generated_number_uses_three_digit_prefix_and_eight_digit_suffix():
    item_number = generate_item_number("128")

    assert item_number.startswith("128")
    assert len(item_number) == 11
    assert item_number.isdigit()


@pytest.mark.parametrize("prefix", [None, "", "12", "1280", "ABC"])
def test_invalid_generation_prefix_is_rejected(prefix):
    with pytest.raises((TypeError, ValueError)):
        generate_item_number(prefix)


def test_generation_preserves_leading_zeroes_in_prefix():
    item_number = generate_item_number("001")

    assert item_number.startswith("001")
    assert len(item_number) == 11
    assert item_number.isdigit()
