"""
环境验证工具 - 验证项目运行所需的依赖和环境配置
"""

import sys
import importlib
import os
from typing import List, Dict
from dotenv import load_dotenv


class EnvironmentChecker:
    """环境检查器"""

    # 必需的Python包
    REQUIRED_PACKAGES = [
        'browser-use',
        'playwright',
        'python-dotenv',
        'jinja2'
    ]

    def __init__(self):
        self.missing_packages = []
        self.missing_env_vars = []
        self.errors = []
        self.required_env_vars = self._load_required_env_vars()

    def _load_required_env_vars(self) -> List[str]:
        """从config_example.env加载必需的环境变量清单"""
        config_file = 'config_example.env'

        if not os.path.exists(config_file):
            print(f"   ⚠️ 未找到 {config_file}，使用默认环境变量清单")
            return ['API_KEY', 'BASE_URL', 'MODEL_STD', 'MODEL_MINI']

        try:
            env_vars = []
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # 跳过空行和注释
                    if not line or line.startswith('#'):
                        continue
                    # 提取环境变量名（等号前面的部分）
                    if '=' in line:
                        var_name = line.split('=')[0].strip()
                        if var_name:
                            env_vars.append(var_name)

            print(f"   ✅ 从 {config_file} 加载了 {len(env_vars)} 个必需环境变量")
            return env_vars

        except Exception as e:
            print(f"   ⚠️ 读取 {config_file} 失败: {e}，使用默认环境变量清单")
            return ['API_KEY', 'BASE_URL', 'MODEL_STD', 'MODEL_MINI']

    def check_python_version(self) -> bool:
        """检查Python版本"""
        print("🐍 检查Python版本...")
        version = sys.version_info
        print(f"   当前版本: {version.major}.{version.minor}.{version.micro}")

        if version.major < 3 or (version.major == 3 and version.minor < 8):
            self.errors.append(f"Python版本过低，需要3.8+，当前版本: {version.major}.{version.minor}")
            return False

        print("   ✅ Python版本满足要求")
        return True

    def check_package_dependencies(self) -> bool:
        """检查包依赖"""
        print("\n📦 检查pip包依赖...")

        all_installed = True
        for package in self.REQUIRED_PACKAGES:
            try:
                # 特殊处理不同的包名和模块名映射
                if package == 'browser-use':
                    import browser_use
                    version = getattr(browser_use, '__version__', 'unknown')
                    print(f"   ✅ {package} (版本: {version})")
                elif package == 'python-dotenv':
                    import dotenv
                    version = getattr(dotenv, '__version__', 'unknown')
                    print(f"   ✅ {package} (版本: {version})")
                else:
                    module = importlib.import_module(package.replace('-', '_'))
                    version = getattr(module, '__version__', 'unknown')
                    print(f"   ✅ {package} (版本: {version})")
            except ImportError:
                self.missing_packages.append(package)
                all_installed = False
                print(f"   ❌ {package} - 未安装")

        return all_installed

    def check_environment_variables(self) -> bool:
        """检查环境变量"""
        print("\n🔧 检查环境变量...")

        # 先尝试加载.env文件
        env_file_exists = os.path.exists('.env')
        if env_file_exists:
            load_dotenv()
            print("   ✅ 找到并加载了.env文件")
        else:
            print("   ⚠️ 未找到.env文件")

        all_present = True
        for env_var in self.required_env_vars:
            value = os.getenv(env_var)
            if value:
                # 对于敏感信息，只显示部分内容
                if 'KEY' in env_var:
                    masked_value = value[:8] + "..." if len(value) > 8 else "***"
                    print(f"   ✅ {env_var}: {masked_value}")
                else:
                    print(f"   ✅ {env_var}: {value}")
            else:
                self.missing_env_vars.append(env_var)
                all_present = False
                print(f"   ❌ {env_var} - 未设置")

        return all_present

    def check_playwright_browsers(self) -> bool:
        """检查Playwright浏览器是否已安装"""
        print("\n🌐 检查Playwright浏览器...")

        try:
            # 尝试导入playwright并检查浏览器状态
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright():
                    # 简单检查浏览器是否可用
                    print("   ✅ Playwright浏览器依赖正常")
                    return True
            except Exception as e:
                print(f"   ⚠️ Playwright浏览器可能未完全安装: {e}")
                print("   💡 运行 'playwright install' 安装浏览器")
                return False

        except Exception as e:
            print(f"   ❌ Playwright浏览器检查失败: {e}")
            return False

    def show_installation_help(self):
        """显示安装帮助信息"""
        print("\n" + "="*60)
        print("🚀 环境配置指南")
        print("="*60)

        if self.missing_packages:
            print("\n📦 安装缺失的Python包:")
            print("   pip install -r requirements.txt")
            print("   或单独安装:")
            for package in self.missing_packages:
                print(f"   pip install {package}")

        if self.missing_env_vars:
            print("\n🔧 配置环境变量:")
            print("   1. 创建.env文件（或设置系统环境变量）")
            print("   2. 添加以下内容:")

            # 从config_example.env读取示例值
            example_values = self._load_example_env_values()

            for env_var in self.missing_env_vars:
                example_value = example_values.get(env_var, 'your_value_here')
                # 对于API_KEY等敏感信息，不显示完整的示例值
                if 'KEY' in env_var and 'XXXXXXXX' in example_value:
                    print(f"   {env_var}=your_actual_api_key_here")
                else:
                    print(f"   {env_var}={example_value}")

        print("\n🌐 安装Playwright浏览器:")
        print("   playwright install")
        print("   playwright install-deps")

    def _load_example_env_values(self) -> Dict[str, str]:
        """从config_example.env加载示例环境变量值"""
        config_file = 'config_example.env'
        example_values = {}

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # 跳过空行和注释
                        if not line or line.startswith('#'):
                            continue
                        # 提取环境变量名和值
                        if '=' in line:
                            var_name, var_value = line.split('=', 1)
                            var_name = var_name.strip()
                            var_value = var_value.strip()
                            if var_name:
                                example_values[var_name] = var_value
            except Exception as e:
                print(f"   ⚠️ 读取示例配置失败: {e}")

        return example_values

    def run_all_checks(self) -> bool:
        """运行所有环境检查"""
        print("🔍 AI WebDriver 环境检查工具")
        print("="*60)

        checks_passed = True

        # 运行各项检查
        checks_passed &= self.check_python_version()
        checks_passed &= self.check_package_dependencies()
        checks_passed &= self.check_environment_variables()
        checks_passed &= self.check_playwright_browsers()

        # 显示检查结果
        print("\n" + "="*60)
        if checks_passed and not self.missing_packages and not self.missing_env_vars:
            print("🎉 所有环境检查通过！可以运行AI WebDriver。")
            return True
        else:
            print("❌ 环境检查发现问题，请按以下指南修复:")
            self.show_installation_help()
            return False


async def run_dynamic_validation():
    """运行动态验证（原有的main函数逻辑）"""
    print("\n🚀 开始动态验证...")
    print("="*60)

    from browser_use import Agent, Browser
    from browser_use.llm import ChatOpenAI

    # 加载环境变量
    load_dotenv()

    # 配置OpenAI兼容的LLM
    llm = ChatOpenAI(
        model=os.getenv("MODEL_STD", "glm-4-flash"),  # 使用智谱AI的模型
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"))

    # 配置页面内容提取的轻量级LLM
    page_extraction_llm = ChatOpenAI(
        model=os.getenv("MODEL_MINI", "glm-4.5-air"),  # 使用智谱AI的轻量模型
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"))

    # 配置浏览器基本模式
    browser = Browser(
        headless=False,  # 显示浏览器窗口
        window_size={
            'width': 1920,
            'height': 1080
        },  # 设置为1080p横向尺寸
    )

    # 定义任务
    task = "访问 https://bigmodel.cn/ 如果页面上有弹窗广告的话，先关闭弹窗广告再进行下一步。点击关于智谱进入关于页面，在关于页面中确认是否有显示这个邮箱：service@zhipuai.cn"

    # 创建Agent，传入配置好的浏览器
    agent = Agent(task=task, llm=llm, page_extraction_llm=page_extraction_llm, browser=browser, use_vision=False)

    # 运行Agent
    await agent.run()


def main():
    """主函数"""
    checker = EnvironmentChecker()

    # 首先进行环境检查
    env_ok = checker.run_all_checks()

    if env_ok:
        # 环境检查通过，运行动态验证
        try:
            import asyncio
            asyncio.run(run_dynamic_validation())
        except KeyboardInterrupt:
            print("\n⚠️ 验证被用户中断")
        except Exception as e:
            print(f"\n❌ 动态验证失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        # 环境检查失败，提示用户修复后重试
        print("\n💡 请修复上述问题后重新运行此脚本")
        sys.exit(1)


if __name__ == "__main__":
    main()
