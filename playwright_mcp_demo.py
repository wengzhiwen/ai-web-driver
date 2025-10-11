"""
Playwright MCP Server 演示 - 展示如何通过MCP协议控制浏览器
这是一个更接近真实MCP使用场景的实现
"""

import asyncio
import json
from typing import Dict, Any, Optional
from dotenv import load_dotenv


class MCPClient:
    """简单的MCP客户端实现"""

    def __init__(self, server_command: list):
        self.server_process = None
        self.server_command = server_command

    async def start_server(self):
        """启动MCP服务器"""
        try:
            self.server_process = await asyncio.create_subprocess_exec(
                *self.server_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            print(f"✅ MCP服务器已启动: {' '.join(self.server_command)}")
            return True
        except Exception as e:
            print(f"❌ 启动MCP服务器失败: {e}")
            return False

    async def send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """发送MCP请求"""
        if not self.server_process:
            raise RuntimeError("MCP服务器未启动")

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {}
        }

        request_json = json.dumps(request) + "\n"
        self.server_process.stdin.write(request_json.encode())
        await self.server_process.stdin.drain()

        # 读取响应
        response_line = await self.server_process.stdout.readline()
        if response_line:
            response = json.loads(response_line.decode().strip())
            return response
        else:
            raise RuntimeError("未收到MCP服务器响应")

    async def close(self):
        """关闭MCP服务器"""
        if self.server_process:
            self.server_process.terminate()
            await self.server_process.wait()


class PlaywrightMCPDemo:
    """Playwright MCP演示类"""

    def __init__(self):
        self.mcp_client = None

    async def initialize(self):
        """初始化MCP连接"""
        # 检查可用的MCP服务器
        server_commands = [
            ["npx", "@modelcontextprotocol/server-playwright"],
            ["playwright-mcp-server"],
            ["mcp-server-playwright"]
        ]

        for cmd in server_commands:
            print(f"🔍 尝试启动MCP服务器: {' '.join(cmd)}")
            self.mcp_client = MCPClient(cmd)

            if await self.mcp_client.start_server():
                # 初始化MCP会话
                try:
                    await self.mcp_client.send_request("initialize", {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        }
                    })
                    print("✅ MCP会话已初始化")
                    return True
                except Exception as e:
                    print(f"❌ MCP会话初始化失败: {e}")
                    await self.mcp_client.close()
                    continue
            else:
                await self.mcp_client.close()
                continue

        print("❌ 无法启动任何MCP服务器")
        return False

    async def navigate_to_page(self, url: str) -> bool:
        """导航到指定页面"""
        try:
            response = await self.mcp_client.send_request("tools/call", {
                "name": "playwright_navigate",
                "arguments": {
                    "url": url
                }
            })

            if response.get("result"):
                print(f"✅ 成功导航到: {url}")
                return True

            print(f"❌ 导航失败: {response.get('error', '未知错误')}")
            return False
        except Exception as e:
            print(f"❌ 导航过程出错: {e}")
            return False

    async def get_page_content(self) -> Optional[str]:
        """获取页面内容"""
        try:
            response = await self.mcp_client.send_request("tools/call", {
                "name": "playwright_get_content",
                "arguments": {}
            })

            if response.get("result"):
                content = response["result"].get("content", "")
                return content

            print(f"❌ 获取页面内容失败: {response.get('error', '未知错误')}")
            return None
        except Exception as e:
            print(f"❌ 获取页面内容出错: {e}")
            return None

    async def click_element(self, selector: str) -> bool:
        """点击页面元素"""
        try:
            response = await self.mcp_client.send_request("tools/call", {
                "name": "playwright_click",
                "arguments": {
                    "selector": selector
                }
            })

            if response.get("result"):
                print(f"✅ 成功点击元素: {selector}")
                return True

            print(f"❌ 点击失败: {response.get('error', '未知错误')}")
            return False
        except Exception as e:
            print(f"❌ 点击元素出错: {e}")
            return False

    async def wait_for_element(self, selector: str, timeout: int = 5000) -> bool:
        """等待元素出现"""
        try:
            response = await self.mcp_client.send_request("tools/call", {
                "name": "playwright_wait_for_selector",
                "arguments": {
                    "selector": selector,
                    "timeout": timeout
                }
            })

            if response.get("result"):
                print(f"✅ 元素已出现: {selector}")
                return True

            print(f"❌ 等待元素超时: {selector}")
            return False
        except Exception as e:
            print(f"❌ 等待元素出错: {e}")
            return False

    async def take_screenshot(self, filename: str = "screenshot.png") -> bool:
        """截图"""
        try:
            response = await self.mcp_client.send_request("tools/call", {
                "name": "playwright_screenshot",
                "arguments": {
                    "path": filename
                }
            })

            if response.get("result"):
                print(f"✅ 截图已保存: {filename}")
                return True

            print(f"❌ 截图失败: {response.get('error', '未知错误')}")
            return False
        except Exception as e:
            print(f"❌ 截图出错: {e}")
            return False

    async def run_demo_task(self):
        """运行演示任务"""
        print("\n🚀 开始Playwright MCP演示任务...")
        print("="*60)

        # 任务：访问智谱AI官网，查找联系邮箱
        task_url = "https://bigmodel.cn/"
        target_email = "service@zhipuai.cn"

        # 1. 导航到目标网站
        print(f"📋 步骤1: 访问 {task_url}")
        if not await self.navigate_to_page(task_url):
            return False

        # 2. 等待页面加载
        await asyncio.sleep(2)

        # 3. 截图保存当前页面
        print("📸 步骤2: 保存首页截图")
        await self.take_screenshot("homepage.png")

        # 4. 获取页面内容
        print("📄 步骤3: 获取页面内容")
        content = await self.get_page_content()
        if content:
            print(f"   页面内容长度: {len(content)} 字符")

        # 5. 查找关于链接的多种选择器
        about_selectors = [
            'a[href*="about"]',
            'a:has-text("关于")',
            'a:has-text("关于智谱")',
            '[class*="nav"] a:has-text("关于")',
            'text="关于"'
        ]

        about_clicked = False
        print("🔍 步骤4: 查找并点击'关于'链接")

        for selector in about_selectors:
            print(f"   尝试选择器: {selector}")
            if await self.wait_for_element(selector, 3000):
                if await self.click_element(selector):
                    about_clicked = True
                    break
            await asyncio.sleep(1)

        if about_clicked:
            print("✅ 成功点击关于链接")
            await asyncio.sleep(2)

            # 6. 在关于页面查找邮箱
            print("📧 步骤5: 在关于页面查找邮箱")
            await self.take_screenshot("about_page.png")

            about_content = await self.get_page_content()
            if about_content and target_email in about_content:
                print(f"✅ 找到目标邮箱: {target_email}")
            else:
                print(f"❌ 未找到目标邮箱: {target_email}")

                # 查找其他可能的联系信息
                contact_patterns = ["@", "邮箱", "联系", "contact", "email"]
                for pattern in contact_patterns:
                    if pattern in about_content:
                        print(f"ℹ️ 发现相关联系信息: {pattern}")
                        break
        else:
            print("❌ 未能找到或点击关于链接")

            # 尝试在首页直接查找邮箱
            if content and target_email in content:
                print(f"ℹ️ 在首页找到目标邮箱: {target_email}")
            else:
                print("ℹ️ 首页也未找到目标邮箱")

        print("\n✅ Playwright MCP演示任务完成")

    async def cleanup(self):
        """清理资源"""
        if self.mcp_client:
            await self.mcp_client.close()


async def main():
    """主函数"""
    print("🎭 Playwright MCP 演示程序")
    print("="*60)

    # 加载环境变量
    load_dotenv()

    demo = PlaywrightMCPDemo()

    try:
        # 初始化MCP连接
        if await demo.initialize():
            # 运行演示任务
            await demo.run_demo_task()
        else:
            print("\n💡 如果MCP服务器未安装，请运行:")
            print("   npm install -g @modelcontextprotocol/server-playwright")

            # 提供fallback方案，直接使用Playwright
            print("\n🔄 使用Playwright直接执行...")
            await run_fallback_demo()

    except KeyboardInterrupt:
        print("\n⚠️ 演示被用户中断")
    except Exception as e:
        print(f"\n❌ 演示执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await demo.cleanup()


async def run_fallback_demo():
    """备用演示：直接使用Playwright"""
    print("\n🔄 使用Playwright直接执行演示任务...")

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

            # 访问网站
            await page.goto("https://bigmodel.cn/", wait_until="networkidle")
            print("✅ 访问智谱AI官网")

            # 截图
            await page.screenshot(path="playwright_direct_homepage.png")
            print("✅ 保存首页截图")

            # 获取内容
            content = await page.content()
            target_email = "service@zhipuai.cn"

            if target_email in content:
                print(f"✅ 在首页找到目标邮箱: {target_email}")
            else:
                print(f"❌ 首页未找到目标邮箱: {target_email}")

            await browser.close()
            print("✅ Playwright直接执行完成")

    except ImportError:
        print("❌ Playwright未安装，请运行: pip install playwright")
    except Exception as e:
        print(f"❌ Playwright执行失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())