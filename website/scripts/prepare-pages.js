const fs = require('fs');
const path = require('path');

const sourceDir = path.join(process.cwd(), '.open-next');
const targetDir = path.join(process.cwd(), '.open-next', 'assets');

// 1. 复制依赖目录
const itemsToCopy = ['cloudflare', 'middleware', 'server-functions', '.build'];
console.log('🔄 开始适配 Cloudflare Pages...');

itemsToCopy.forEach(item => {
    const srcPath = path.join(sourceDir, item);
    const destPath = path.join(targetDir, item);
    if (fs.existsSync(srcPath)) {
        try {
            fs.cpSync(srcPath, destPath, { recursive: true, force: true });
            console.log(`   ✅ 已复制依赖: ${item}`);
        } catch (e) {
            console.warn(`   ⚠️ 复制 ${item} 失败 (可能不需要):`, e.message);
        }
    }
});

// 2. 处理核心 Worker 逻辑
const workerSrc = path.join(sourceDir, 'worker.js');
const appWorkerDest = path.join(targetDir, 'app-worker.js');

// 3. 创建新的入口文件 _worker.js
// 🔴 修正点：使用 import appWorker from ... (默认导入)
const wrapperWorkerContent = `
import appWorker from "./app-worker.js";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    // 🔍 策略：如果是静态资源路径，优先查 ASSETS
    // 涵盖 Next.js 静态资源 (_next) 和 public 目录资源 (含扩展名的文件)
    if (url.pathname.startsWith('/_next/') || 
        url.pathname.startsWith('/static/') || 
        url.pathname.includes('.')) {
      
      try {
        if (env.ASSETS) {
          const asset = await env.ASSETS.fetch(request);
          // 只有找到文件 (2xx/3xx) 才返回，404 则继续交给 Next.js 处理
          if (asset.status < 400) {
            return asset;
          }
        }
      } catch (e) {
        console.warn("Asset fetch failed", e);
      }
    }

    // 🚀 调用原始 Worker 的 fetch 方法
    return appWorker.fetch(request, env, ctx);
  }
};
`;

try {
    if (fs.existsSync(workerSrc)) {
        // 1. 移动原始 worker
        fs.copyFileSync(workerSrc, appWorkerDest);
        console.log('   ✅ 原始 Worker 已重命名为 app-worker.js');

        // 2. 写入新的包装器 _worker.js
        fs.writeFileSync(path.join(targetDir, '_worker.js'), wrapperWorkerContent);
        console.log('   ✅ 已生成静态资源拦截器 (_worker.js)');
        
        console.log('🎉 适配完成！准备部署...');
    } else {
        console.error('❌ 错误: 未找到 .open-next/worker.js');
        process.exit(1);
    }
} catch (e) {
    console.error('❌ 文件操作失败:', e);
    process.exit(1);
}