<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <div class="brand">📘 AI 学习助手</div>
      <div class="sub">本地学习管理 · 数据只存在这台电脑上</div>

      <el-tabs v-model="tab" stretch>
        <el-tab-pane label="登录" name="login">
          <el-form @submit.prevent="doLogin">
            <el-form-item>
              <el-input v-model="loginForm.username" placeholder="用户名" size="large" autofocus>
                <template #prefix><el-icon><User /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <el-input v-model="loginForm.password" type="password" placeholder="密码" size="large" show-password>
                <template #prefix><el-icon><Lock /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-button type="primary" size="large" class="wide" :loading="busy" native-type="submit">
              登 录
            </el-button>
          </el-form>
          <el-alert class="hint" type="info" :closable="false"
            title="旧版本的数据都在演示账号里" description="用户名 demo　密码 demo123　登录后即可看到" />
        </el-tab-pane>

        <el-tab-pane label="注册" name="register">
          <el-form @submit.prevent="doRegister">
            <el-form-item>
              <el-input v-model="regForm.username" placeholder="用户名（2~32 字符，不含空格）" size="large">
                <template #prefix><el-icon><User /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <el-input v-model="regForm.display_name" placeholder="昵称（可选，显示在侧边栏）" size="large">
                <template #prefix><el-icon><Postcard /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <el-input v-model="regForm.password" type="password" placeholder="密码（至少 6 位）" size="large" show-password>
                <template #prefix><el-icon><Lock /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <el-input v-model="regForm.password2" type="password" placeholder="再输一遍密码" size="large" show-password>
                <template #prefix><el-icon><Lock /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-button type="success" size="large" class="wide" :loading="busy" native-type="submit">
              创建账号
            </el-button>
          </el-form>
          <el-alert class="hint" type="warning" :closable="false"
            title="每个账号的数据完全独立" description="资料、知识点、错题本都只属于当前账号；这只是一个本地隔离，不是联网认证。" />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, Postcard } from '@element-plus/icons-vue'
import api, { auth } from '../api'

const router = useRouter()
const tab = ref('login')
const busy = ref(false)
const loginForm = reactive({ username: '', password: '' })
const regForm = reactive({ username: '', display_name: '', password: '', password2: '' })

function enter(data) {
  auth.save(data.token, data.user)
  ElMessage.success(`欢迎，${data.user.display_name || data.user.username}`)
  router.push('/')
}

async function doLogin() {
  if (!loginForm.username || !loginForm.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  busy.value = true
  try {
    enter(await api.login({ ...loginForm }))
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    busy.value = false
  }
}

async function doRegister() {
  if (regForm.password !== regForm.password2) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }
  busy.value = true
  try {
    enter(await api.register({ ...regForm }))
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #e8f1ff 0%, #f5f7fa 60%);
}
.login-card { width: 420px; padding: 8px 12px 4px; }
.brand { font-size: 22px; font-weight: 700; color: #409eff; text-align: center; }
.sub { font-size: 13px; color: #909399; text-align: center; margin: 6px 0 18px; }
.wide { width: 100%; margin-top: 4px; }
.hint { margin-top: 16px; }
</style>
