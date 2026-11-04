/**
 * 复制文本到剪贴板，兼容非 HTTPS 部署。
 *
 * navigator.clipboard 只在「安全上下文」可用（HTTPS 或 localhost），
 * 部署到 http://<内网IP>:端口 时会静默不可用，因此降级到 execCommand('copy')。
 * 注意：execCommand 必须保持同步执行，否则 iOS Safari 会丢失用户手势。
 */
export function copyToClipboard(text) {
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    // 返回 promise：调用方记得 await
    return navigator.clipboard
      .writeText(text)
      .then(() => true)
      .catch(() => legacyCopy(text))
  }
  return Promise.resolve(legacyCopy(text))
}

function legacyCopy(text) {
  const holder = document.createElement('textarea')
  holder.value = text
  holder.setAttribute('readonly', '')
  holder.style.position = 'fixed'
  holder.style.top = '0'
  holder.style.left = '0'
  holder.style.width = '1px'
  holder.style.height = '1px'
  holder.style.padding = '0'
  holder.style.border = 'none'
  holder.style.opacity = '0'
  document.body.appendChild(holder)

  let ok = false
  try {
    holder.focus()
    holder.select()
    holder.setSelectionRange(0, text.length)
    ok = document.execCommand('copy')
  } catch {
    ok = false
  } finally {
    document.body.removeChild(holder)
  }
  return ok
}
