import pytest


def test_generated_number_uses_three_digit_prefix_and_eight_digit_suffix(
    generator_api,
    empty_golden_record,
):
    item_number = generator_api("128", empty_golden_record)

    assert item_number.startswith("128")
    assert len(item_number) == 11
    assert item_number.isdigit()


@pytest.mark.parametrize("prefix", [None, "", "12", "1280", "ABC"])
def test_invalid_generation_prefix_is_rejected(
    generator_api,
    empty_golden_record,
    prefix,
):
    with pytest.raises((TypeError, ValueError)):
        generator_api(prefix, empty_golden_record)


def test_generation_preserves_leading_zeroes_in_prefix(
    generator_api,
    empty_golden_record,
):
    item_number = generator_api("001", empty_golden_record)

    assert item_number.startswith("001")
    assert len(item_number) == 11
    assert item_number.isdigit()
