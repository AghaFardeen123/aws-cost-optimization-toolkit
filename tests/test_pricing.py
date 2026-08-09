import pytest

from cost_audit import pricing


def test_ec2_monthly_cost_known_type():
    cost = pricing.ec2_monthly_cost("t3.micro")
    assert cost == pytest.approx(0.0104 * 730, abs=0.01)


def test_ec2_monthly_cost_unknown_type_raises():
    with pytest.raises(KeyError):
        pricing.ec2_monthly_cost("m6i.32xlarge")


def test_ebs_monthly_cost_scales_with_size():
    assert pricing.ebs_monthly_cost(100) == pytest.approx(8.0, abs=0.01)
    assert pricing.ebs_monthly_cost(200) == pytest.approx(16.0, abs=0.01)


def test_recommended_instance_type_steps_down_one_tier():
    assert pricing.recommended_instance_type("t3.large") == "t3.medium"
    assert pricing.recommended_instance_type("t3.medium") == "t3.small"


def test_recommended_instance_type_none_at_floor():
    assert pricing.recommended_instance_type("t3.micro") is None


def test_downsizing_always_reduces_cost():
    for instance_type, smaller_type in pricing.DOWNSIZE_MAP.items():
        assert pricing.ec2_monthly_cost(smaller_type) < pricing.ec2_monthly_cost(instance_type)
