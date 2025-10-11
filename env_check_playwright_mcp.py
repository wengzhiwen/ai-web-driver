"""
基于 Playwright MCP Server 的环境验证工具 - 与 browser-use 版本对比
"""

import sys
import subprocess
import importlib
import os
import asyncio
from typing import List, Dict
from dotenv import load_dotenv
from playwright.async_api import async_playwright


class PlaywrightMCPEnvironmentChecker:
    """基于 Playwright MCP Server 的环境检查器"""

    # 必需的Python包
    REQUIRED_PACKAGES = [
        'playwright',
        'python-dotenv',
        'mcp',  # MCP client library
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
                if package == 'python-dotenv':
                    import dotenv
                    version = getattr(dotenv, '__version__', 'unknown')
                    print(f"   ✅ {package} (版本: {version})")
                elif package == 'mcp':
                    # 检查MCP相关包
                    try:
                        import mcp  # pylint: disable=import-outside-toplevel
                        print(f"   ✅ {package} (MCP Client)")
                    except ImportError as exc:
                        # 如果没有mcp包，检查其他MCP相关包
                        try:
                            from mcp import ClientSession, StdioServerParameters  # pylint: disable=import-outside-toplevel
                            print(f"   ✅ {package} (MCP Client)")
                        except ImportError:
                            raise ImportError("MCP client not found") from exc
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

                with sync_playwright() as p:
                    # 简单检查浏览器是否可用
                    if p.chromium and p.firefox and p.webkit:
                        print("   ✅ Playwright浏览器依赖正常 (Chromium, Firefox, WebKit)")
                        return True

                    print("   ⚠️ 部分Playwright浏览器未安装")
                    return False
            except Exception as e:
                print(f"   ⚠️ Playwright浏览器可能未完全安装: {e}")
                print("   💡 运行 'playwright install' 安装浏览器")
                return False

        except Exception as e:
            print(f"   ❌ Playwright浏览器检查失败: {e}")
            return False

    def check_mcp_server(self) -> bool:
        """检查MCP服务器是否可用"""
        print("\n🔌 检查MCP服务器...")

        # 检查常见的MCP服务器路径
        mcp_server_paths = ['npx @modelcontextprotocol/server-playwright', 'mcp-server-playwright', 'playwright-mcp-server']

        for server_path in mcp_server_paths:
            try:
                # 尝试运行服务器检查命令
                subprocess.run(server_path.split() + ['--help'], capture_output=True, text=True, timeout=5, check=False)
                print(f"   ✅ MCP服务器可用: {server_path}")
                return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        print("   ⚠️ 未找到可用的Playwright MCP服务器")
        print("   💡 请安装: npm install -g @modelcontextprotocol/server-playwright")
        return False

    def show_installation_help(self):
        """显示安装帮助信息"""
        print("\n" + "=" * 60)
        print("🚀 Playwright MCP 环境配置指南")
        print("=" * 60)

        if self.missing_packages:
            print("\n📦 安装缺失的Python包:")
            print("   pip install -r requirements.txt")
            print("   或单独安装:")
            for package in self.missing_packages:
                if package == 'mcp':
                    print("   pip install mcp-client")
                else:
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

        print("\n🔌 安装Playwright MCP服务器:")
        print("   npm install -g @modelcontextprotocol/server-playwright")
        print("   # 或者")
        print("   npx @modelcontextprotocol/server-playwright")

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
        print("🔍 Playwright MCP 环境检查工具")
        print("=" * 60)

        checks_passed = True

        # 运行各项检查
        checks_passed &= self.check_python_version()
        checks_passed &= self.check_package_dependencies()
        checks_passed &= self.check_environment_variables()
        checks_passed &= self.check_playwright_browsers()
        checks_passed &= self.check_mcp_server()

        # 显示检查结果
        print("\n" + "=" * 60)
        if checks_passed and not self.missing_packages and not self.missing_env_vars:
            print("🎉 所有环境检查通过！可以使用Playwright MCP Server。")
            return True

        print("❌ 环境检查发现问题，请按以下指南修复:")
        self.show_installation_help()
        return False


async def close_popups(page):
    """关闭弹窗广告"""
    print("🔍 检查弹窗广告...")
    popup_selectors = [
        '[class*="popup"]', '[class*="modal"]', '[class*="dialog"]', '[id*="popup"]', '[id*="modal"]', '[class*="close"]', '.ad', '.advertisement',
        '[class*="banner"]'
    ]

    for selector in popup_selectors:
        try:
            popup = await page.wait_for_selector(selector, timeout=2000)
            if popup:
                # 尝试找到关闭按钮
                close_btn = await popup.query_selector('[class*="close"], .close, [aria-label*="close"]')
                if close_btn:
                    await close_btn.click()
                    print("   ✅ 已关闭弹窗广告")
                    return True
        except Exception:
            continue

    print("   ℹ️ 未发现需要关闭的弹窗广告")
    return False


async def click_about_link(page):
    """点击关于链接"""
    print("🔍 查找'关于智谱'链接...")
    about_selectors = ['a[href*="about"]', 'a:has-text("关于")', 'a:has-text("关于智谱")', '[class*="about"] a', '[class*="nav"] a:has-text("关于")']

    for selector in about_selectors:
        try:
            about_link = await page.wait_for_selector(selector, timeout=3000)
            if about_link:
                await about_link.click()
                print("   ✅ 已点击'关于智谱'链接")
                return True
        except Exception:
            continue

    # 尝试查找包含"关于"文本的元素
    about_elements = await page.query_selector_all('*:has-text("关于")')
    for element in about_elements:
        try:
            await element.click()
            print("   ✅ 已点击包含'关于'的元素")
            return True
        except Exception:
            continue

    print("   ⚠️ 未找到'关于智谱'链接")
    return False


async def check_email_on_page(page, target_email="service@zhipuai.cn"):
    """检查页面上的邮箱"""
    print(f"🔍 在关于页面查找邮箱: {target_email}")
    page_content = await page.content()

    if target_email in page_content:
        print(f"   ✅ 找到邮箱: {target_email}")
        return True

    print(f"   ❌ 未找到邮箱: {target_email}")

    # 尝试其他邮箱格式
    email_patterns = ["service@", "contact@", "support@", "邮箱"]
    for pattern in email_patterns:
        if pattern in page_content:
            print(f"   ℹ️ 找到类似联系信息: {pattern}")
            break
    return False


async def run_playwright_mcp_validation():
    """使用Playwright MCP Server运行动态验证"""
    print("\n🚀 开始Playwright MCP动态验证...")
    print("=" * 60)

    # 加载环境变量
    load_dotenv()

    # 定义任务 - 与browser-use版本相同
    task = "访问 https://bigmodel.cn/ 如果页面上有弹窗广告的话，先关闭弹窗广告再进行下一步。点击关于智谱进入关于页面，在关于页面中确认是否有显示这个邮箱：service@zhipuai.cn"

    print(f"📋 任务: {task}")

    # 启动Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        try:
            # 访问目标网站
            print("🌐 正在访问 https://bigmodel.cn/...")
            await page.goto("https://bigmodel.cn/", wait_until="networkidle")

            # 执行任务步骤
            await close_popups(page)
            about_clicked = await click_about_link(page)

            if about_clicked:
                # 等待页面加载
                await page.wait_for_timeout(2000)
                await check_email_on_page(page)
            else:
                print("   ❌ 无法进入关于页面")

        except Exception as e:
            print(f"❌ 执行过程中出错: {e}")

        finally:
            await browser.close()

    print("\n✅ Playwright MCP 验证完成")


def main():
    """主函数"""
    checker = PlaywrightMCPEnvironmentChecker()

    # 首先进行环境检查
    env_ok = checker.run_all_checks()

    if env_ok:
        # 环境检查通过，运行动态验证
        try:
            asyncio.run(run_playwright_mcp_validation())
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
