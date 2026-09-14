"""
Pytest configuration - 测试配置

定义自定义标记：
- integration: 端到端集成测试，需要真实API密钥，默认不运行
- slow: 慢速测试，默认不运行
- benchmark: 基准测试，需要大量API调用

运行方式：
- 只运行单元测试：pytest tests/（默认）
- 运行所有测试：pytest tests/ -m "integration or not integration"
- 只运行集成测试：pytest tests/ -m integration
- 跳过慢速测试：pytest tests/ -m "not slow"
"""
import pytest
import os


def pytest_configure(config):
    """注册自定义标记"""
    config.addinivalue_line(
        "markers", "integration: 端到端集成测试，需要真实API密钥"
    )
    config.addinivalue_line(
        "markers", "slow: 慢速测试，需要较长时间运行"
    )
    config.addinivalue_line(
        "markers", "benchmark: 基准测试，需要大量API调用"
    )


def pytest_collection_modifyitems(config, items):
    """默认跳过集成测试，除非显式指定"""
    if not config.getoption("-m"):
        # 如果没有指定-m，默认跳过integration测试
        skip_integration = pytest.mark.skip(reason="需要 -m integration 才能运行集成测试")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)


@pytest.fixture(scope="session")
def api_key():
    """
    获取API密钥（用于集成测试）

    从环境变量 TRANSIT_TRUTH_TEST_API_KEY 获取。
    如果未设置，跳过集成测试。
    """
    key = os.getenv("TRANSIT_TRUTH_TEST_API_KEY")
    if not key:
        pytest.skip("未设置 TRANSIT_TRUTH_TEST_API_KEY 环境变量，跳过集成测试")
    return key


@pytest.fixture(scope="session")
def base_url():
    """
    获取API基础URL（用于集成测试）

    从环境变量 TRANSIT_TRUTH_TEST_BASE_URL 获取。
    默认使用 https://api.openai.com/v1
    """
    return os.getenv("TRANSIT_TRUTH_TEST_BASE_URL", "https://api.openai.com/v1")


@pytest.fixture(scope="session")
def test_model():
    """
    获取测试模型名称（用于集成测试）

    从环境变量 TRANSIT_TRUTH_TEST_MODEL 获取。
    默认使用 gpt-4o-mini
    """
    return os.getenv("TRANSIT_TRUTH_TEST_MODEL", "gpt-4o-mini")
