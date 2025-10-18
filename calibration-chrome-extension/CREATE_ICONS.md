# 图标生成说明

由于Chrome扩展需要图标文件才能正常加载，我已经创建了以下解决方案：

## 临时解决方案

已经移除了manifest.json中的图标配置，扩展现在可以正常加载。Chrome会使用默认图标。

## 生成自定义图标（可选）

如果您想添加自定义图标，请按以下步骤操作：

### 方法1：使用在线图标生成器
1. 访问 [Favicon.io](https://favicon.io/) 或类似网站
2. 上传一个简单的图片或使用文字生成器
3. 下载16x16、48x48、128x128尺寸的PNG文件
4. 将文件重命名为：icon16.png、icon48.png、icon128.png
5. 放入 `icons/` 目录

### 方法2：使用提供的HTML生成器
1. 在浏览器中打开 `create-icons.html`
2. 点击下载链接获取三个图标文件
3. 将文件放入 `icons/` 目录
4. 恢复manifest.json中的图标配置

### 方法3：手动创建
使用任何图像编辑软件创建：
- **icon16.png**: 16x16像素
- **icon48.png**: 48x48像素
- **icon128.png**: 128x128像素

建议使用蓝色主题(#4f46e5)，包含瞄准图标。

## 恢复图标配置

如果您添加了图标文件，请在manifest.json中恢复以下配置：

```json
"icons": {
  "16": "icons/icon16.png",
  "48": "icons/icon48.png",
  "128": "icons/icon128.png"
},
```

将上述配置添加到manifest.json中的`action`字段之前。