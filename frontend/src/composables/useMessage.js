import { reactive, onUnmounted } from 'vue'

/**
 * 统一的消息提示 composable
 * 解决多组件重复实现 + setTimeout 未清理的内存泄漏问题
 *
 * @param {number} duration 显示时长（毫秒），默认 3000
 * @returns {{ message: {text:string,type:string}, showMessage: (text:string, type?:string)=>void, clearMessage: ()=>void }}
 */
export function useMessage(duration = 3000) {
  const message = reactive({ text: '', type: '' })
  let timer = null

  function clearMessage() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    message.text = ''
    message.type = ''
  }

  function showMessage(text, type = 'success') {
    if (timer) clearTimeout(timer)
    message.text = text
    message.type = type
    timer = setTimeout(() => {
      timer = null
      message.text = ''
      message.type = ''
    }, duration)
  }

  onUnmounted(clearMessage)

  return { message, showMessage, clearMessage }
}
