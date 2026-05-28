<template>
  <div class="my-container">
    <header class="my-hero">
      <span class="section-eyebrow">
        <van-icon name="manager-o" size="13" />
        账户中心
      </span>
      <h1>{{ $t('my.title') }}</h1>
    </header>

    <section class="user-card" @click="goToProfile">
      <div class="avatar-ring">
        <van-image
          v-if="userInfo?.avatar"
          round
          width="68"
          height="68"
          :src="avatarUrl"
        />
        <div v-else class="avatar-fallback">{{ avatarInitial }}</div>
      </div>
      <div class="info">
        <div class="username">{{ isLogin && userInfo ? userInfo.username : $t('my.notLoggedIn') }}</div>
        <div class="desc">{{ isLogin ? (userBio || $t('profile.bio')) : '登录后同步会话、知识库与个人设置' }}</div>
        <div v-if="isLogin" class="status-row">
          <span>
            <span class="status-dot"></span>
            已登录
          </span>
          <span v-if="userStore.isAdmin">管理员</span>
        </div>
        <div v-else class="auth-actions">
          <van-button type="primary" size="small" @click.stop="goToLogin">{{ $t('my.goToLogin') }}</van-button>
          <van-button plain size="small" @click.stop="goToRegister">{{ $t('my.goToRegister') }}</van-button>
        </div>
      </div>
      <van-icon v-if="isLogin" name="arrow" class="arrow-icon" />
    </section>

    <section class="account-stats">
      <div>
        <span>会话</span>
        <strong>同步</strong>
      </div>
      <div>
        <span>知识库</span>
        <strong>可用</strong>
      </div>
      <div>
        <span>语言</span>
        <strong>中/英</strong>
      </div>
    </section>

    <div class="menu-list">
      <van-cell-group inset class="modern-cell-group">
        <van-cell :title="$t('my.notifications')" label="系统通知和服务消息" icon="bell" is-link />
        <van-cell :title="$t('my.settings')" label="主题、语言和隐私设置" icon="setting-o" is-link @click="goToSettings" />
        <van-cell v-if="isLogin" :title="$t('my.logout')" label="退出当前账号" icon="close" @click="handleLogout" />
      </van-cell-group>
    </div>
    <tab-bar />
  </div>
</template>

<script setup>
import { onMounted } from 'vue';
import { useUserStore } from '../store/user';
import { useRouter } from 'vue-router';
import { computed, ref } from 'vue';
import { showDialog, showToast } from 'vant';
import TabBar from '../components/TabBar.vue';
import { useI18n } from 'vue-i18n';

const userStore = useUserStore();
const router = useRouter();
const { t } = useI18n();

// 从store获取用户信息和登录状态
const userInfo = computed(() => userStore.userInfo);
const isLogin = computed(() => userStore.getLoginStatus);
const userBio = computed(() => userStore.getUserBio || t('profile.bio'));
const avatarUrl = computed(() =>
  userInfo.value?.avatar ? `http://localhost:8001${userInfo.value.avatar}` : ''
);
const avatarInitial = computed(() => {
  const name = userInfo.value?.username || 'AI';
  return name.slice(0, 1).toUpperCase();
});

// 跳转到登录页
const goToLogin = () => {
  router.push('/login?redirect=/my');
};

// 跳转到注册页
const goToRegister = () => {
  router.push('/register');
};

// 跳转到个人信息页
const goToProfile = () => {
  if (isLogin.value) {
    router.push('/profile');
  }
};



// 跳转到设置页面
const goToSettings = () => {
  router.push('/settings');
};

// 退出登录
const handleLogout = () => {
  showDialog({
    title: t('common.confirm'),
    message: t('my.logout') + '?',
    showCancelButton: true,
  }).then((action) => {
    if (action === 'confirm') {
      userStore.logout();
      router.push('/login');
    }
  });
};

// 获取用户信息
onMounted(async () => {
  try {
    await userStore.getUserInfoDetail();
  } catch (error) {
    console.error('获取用户信息失败:', error);
  }
});
</script>

<style scoped>
.my-container {
  --page-bg: #f5f7f8;
  --surface: #ffffff;
  --ink: #16202a;
  --muted: #6b7684;
  --line: #dfe7ed;
  --primary: #1d6fe8;
  --teal: #178c83;
  --amber: #b9851d;

  min-height: 100dvh;
  padding-bottom: calc(58px + env(safe-area-inset-bottom));
  background: linear-gradient(180deg, #f8faf9 0%, var(--page-bg) 46%, #eef3f5 100%);
  color: var(--ink);
}

.my-hero {
  padding: 18px 18px 10px;
}

.section-eyebrow {
  display: inline-flex;
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--teal);
  font-size: 12px;
  font-weight: 700;
}

.my-hero h1 {
  margin: 4px 0 0;
  font-size: 25px;
  line-height: 1.15;
  letter-spacing: 0;
}

.user-card {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 6px 14px 12px;
  padding: 16px;
  border: 1px solid rgba(199, 213, 223, 0.72);
  border-radius: 8px;
  background: linear-gradient(135deg, #ffffff 0%, #eef7f6 100%);
  box-shadow: 0 12px 28px rgba(39, 73, 94, 0.08);
  position: relative;
}

.avatar-ring {
  display: grid;
  place-items: center;
  flex: 0 0 76px;
  width: 76px;
  height: 76px;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: inset 0 0 0 1px rgba(199, 213, 223, 0.8), 0 10px 20px rgba(35, 56, 74, 0.09);
}

.avatar-fallback {
  display: grid;
  place-items: center;
  width: 68px;
  height: 68px;
  border-radius: 50%;
  background: linear-gradient(135deg, #123451 0%, #1d6fe8 100%);
  color: #ffffff;
  font-size: 26px;
  font-weight: 850;
}

.arrow-icon {
  flex-shrink: 0;
  color: #8aa0b2;
}

.info {
  flex: 1;
  min-width: 0;
}

.username {
  overflow: hidden;
  color: #1c2a35;
  font-size: 20px;
  font-weight: 850;
  line-height: 1.25;
  margin-bottom: 4px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.desc {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.45;
}

.status-row {
  display: flex;
  gap: 8px;
  margin-top: 9px;
}

.status-row span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 7px;
  border-radius: 999px;
  background: #e7f5f2;
  color: #0e6d66;
  font-size: 11px;
  font-weight: 800;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #18b394;
}

.auth-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.auth-actions .van-button {
  border-radius: 8px;
}

.account-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 0 14px 14px;
}

.account-stats > div {
  padding: 11px 8px;
  border: 1px solid rgba(199, 213, 223, 0.72);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 8px 18px rgba(39, 73, 94, 0.05);
  text-align: center;
}

.account-stats span {
  display: block;
  color: var(--amber);
  font-size: 11px;
  font-weight: 800;
}

.account-stats strong {
  display: block;
  margin-top: 3px;
  color: var(--ink);
  font-size: 14px;
}

.menu-list {
  margin: 0 14px;
}

.modern-cell-group {
  overflow: hidden;
  border: 1px solid rgba(199, 213, 223, 0.72);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 24px rgba(39, 73, 94, 0.06);
}

.modern-cell-group :deep(.van-cell) {
  padding: 14px;
}

.modern-cell-group :deep(.van-cell__title) {
  color: var(--ink);
  font-weight: 800;
}

.modern-cell-group :deep(.van-cell__label) {
  color: var(--muted);
}

@media screen and (max-width: 380px) {
  .my-hero {
    padding: 15px 13px 8px;
  }

  .my-hero h1 {
    font-size: 22px;
  }

  .user-card,
  .account-stats,
  .menu-list {
    margin-left: 10px;
    margin-right: 10px;
  }
}
</style>
