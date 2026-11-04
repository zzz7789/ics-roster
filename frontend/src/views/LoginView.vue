<script setup>
import { ref } from 'vue'
import { api } from '../api/client.js'

const emit = defineEmits(['success'])

const username = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')

async function submit() {
  if (!username.value.trim() || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const user = await api.login(username.value.trim(), password.value)
    emit('success', user)
  } catch (e) {
    error.value = e.status === 401 ? '用户名或密码错误' : `登录失败：${e.message}`
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="submit">
      <h1>ics-roster</h1>
      <p class="muted small">多人排班 · ICS 订阅</p>

      <label class="field">
        <span>用户名</span>
        <input v-model="username" autocomplete="username" placeholder="admin" />
      </label>
      <label class="field">
        <span>密码</span>
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          placeholder="请输入密码"
        />
      </label>

      <p v-if="error" class="login-error">{{ error }}</p>

      <button class="primary block" :disabled="busy">{{ busy ? '登录中…' : '登录' }}</button>
      <p class="muted small hint">
        首次部署时密码会打印在服务日志里，登录后请及时修改。
      </p>
    </form>
  </div>
</template>
