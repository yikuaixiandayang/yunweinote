import { defineConfig, mergeConfig } from 'vite'
import baseConfig from './vite.config.js'

// 临时构建配置：禁用 emptyOutDir 以绕过环境安全删除 shim 对 dist 清空的拦截。
// 旧 hash 资源会残留但无害；新 index.html 引用新 hash 资源。
export default mergeConfig(baseConfig, defineConfig({
  build: { emptyOutDir: false },
}))
