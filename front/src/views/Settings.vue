<template>
  <workbench-layout page-class="settings-workbench" sidebar-label="设置导航" context-label="设置上下文" single-content>
    <template #rail>
      <desktop-rail />
    </template>

    <template #sidebar>
      <div class="settings-side-header">
        <span class="side-eyebrow">偏好设置</span>
        <h2>{{ $t('settings.title') }}</h2>
      </div>
      <div class="settings-side-list">
        <button class="settings-side-item active" type="button" @click="showThemePopup = true">
          <van-icon name="brush-o" size="16" />
          {{ $t('settings.themeCustomization') }}
        </button>
        <button class="settings-side-item" type="button" @click="showLanguagePopup = true">
          <van-icon name="exchange" size="16" />
          {{ $t('settings.languageSettings') }}
        </button>
        <button class="settings-side-item" type="button">
          <van-icon name="shield-o" size="16" />
          {{ $t('settings.privacySettings') }}
        </button>
      </div>
    </template>

    <div class="settings-container">
    <van-nav-bar
      :title="$t('settings.title')"
      left-arrow
      @click-left="onClickLeft"
    />
    
    <div class="settings-list">
      <van-cell-group inset :title="$t('settings.personalization')">
        <van-cell :title="$t('settings.themeCustomization')" is-link @click="showThemePopup = true" />
        <van-cell :title="$t('settings.languageSettings')" is-link @click="showLanguagePopup = true" />
      </van-cell-group>
      
      <van-cell-group inset :title="$t('settings.account')">
        <van-cell :title="$t('settings.privacySettings')" is-link />
        <van-cell :title="$t('settings.notificationSettings')" is-link />
        <van-cell :title="$t('settings.aboutUs')" is-link />
      </van-cell-group>
    </div>
    
    <!-- 主题选择弹出层 -->
    <van-popup
      v-model:show="showThemePopup"
      position="bottom"
      round
      :style="{ height: '40%' }"
    >
      <div class="popup-title">{{ $t('settings.selectTheme') }}</div>
      <div class="theme-list">
        <div 
          v-for="theme in themeList" 
          :key="theme.id" 
          class="theme-item"
          :class="{ active: currentTheme === theme.id }"
          @click="changeTheme(theme.id)"
        >
          <div class="theme-color" :style="{ backgroundColor: theme.primaryColor }"></div>
          <div class="theme-name">{{ theme.name }}</div>
        </div>
      </div>
    </van-popup>
    
    <!-- 语言选择弹出层 -->
    <van-popup
      v-model:show="showLanguagePopup"
      position="bottom"
      round
      :style="{ height: '40%' }"
    >
      <div class="popup-title">{{ $t('settings.selectLanguage') }}</div>
      <van-radio-group v-model="currentLanguage">
        <van-cell-group inset>
          <van-cell 
            v-for="lang in languageOptions" 
            :key="lang.value" 
            :title="lang.label" 
            clickable 
            @click="currentLanguage = lang.value"
            :class="{ 'language-active': currentLanguage === lang.value }"
          >
            <template #right-icon>
              <van-radio :name="lang.value" />
            </template>
          </van-cell>
        </van-cell-group>
      </van-radio-group>
      <div class="popup-footer">
        <van-button type="primary" block @click="changeLanguage">{{ $t('common.confirm') }}</van-button>
      </div>
    </van-popup>
    </div>

    <template #context>
      <section class="settings-context-card">
        <div class="settings-context-title">
          <h3>当前偏好</h3>
        </div>
        <div class="settings-context-list">
          <div><span>主题</span><strong>{{ currentTheme }}</strong></div>
          <div><span>语言</span><strong>{{ currentLanguage }}</strong></div>
          <div><span>应用范围</span><strong>本机</strong></div>
        </div>
      </section>

      <section class="settings-context-card">
        <div class="settings-context-title">
          <h3>快捷操作</h3>
        </div>
        <button class="settings-context-action" type="button" @click="showThemePopup = true">切换主题</button>
        <button class="settings-context-action" type="button" @click="showLanguagePopup = true">切换语言</button>
      </section>
    </template>
  </workbench-layout>
</template>

<script setup>
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { showToast } from 'vant';
import DesktopRail from '../components/DesktopRail.vue';
import WorkbenchLayout from '../components/WorkbenchLayout.vue';
import { useThemeStore } from '../store/theme';
import { useI18n } from 'vue-i18n';
import { useLanguageStore } from '../store/language';

const router = useRouter();
const themeStore = useThemeStore();
const languageStore = useLanguageStore();
const { t, locale } = useI18n();

// 返回上一页
const onClickLeft = () => {
  router.back();
};

// 主题相关
const showThemePopup = ref(false);
const themeList = computed(() => themeStore.getAllThemes);
const currentTheme = computed(() => themeStore.getCurrentTheme);

// 切换主题
const changeTheme = (themeId) => {
  themeStore.setTheme(themeId);
  showToast(t('settings.themeChanged'));
  showThemePopup.value = false;
};

// 语言相关
const showLanguagePopup = ref(false);
const currentLanguage = ref(languageStore.getCurrentLanguage);
const languageOptions = [
  { label: '简体中文', value: 'zh-CN' },
  { label: 'English', value: 'en-US' }
];

// 切换语言
const changeLanguage = () => {
  languageStore.setLanguage(currentLanguage.value);
  locale.value = currentLanguage.value;
  showLanguagePopup.value = false;
  showToast(t('settings.languageChanged'));
  // 强制刷新页面以应用语言更改
  window.location.reload();
};
</script>

<style scoped>
.settings-side-header {
  margin-bottom: 14px;
}

.side-eyebrow {
  color: var(--workbench-teal, #178c83);
  font-size: 12px;
  font-weight: 800;
}

.settings-side-header h2 {
  margin: 2px 0 0;
  color: var(--workbench-ink, #16202a);
  font-size: 19px;
  line-height: 1.2;
}

.settings-side-list {
  display: grid;
  gap: 8px;
}

.settings-side-item,
.settings-context-action {
  display: flex;
  align-items: center;
  width: 100%;
  border: 0;
  cursor: pointer;
}

.settings-side-item {
  gap: 8px;
  min-height: 42px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: var(--workbench-muted, #6b7684);
  font-size: 13px;
  font-weight: 800;
}

.settings-side-item.active,
.settings-side-item:hover {
  border-color: #c8ddf4;
  background: #ffffff;
  color: var(--workbench-primary, #1d6fe8);
  box-shadow: 0 10px 28px rgba(31, 122, 224, 0.08);
}

.settings-context-card {
  margin-bottom: 14px;
  padding: 14px;
  border: 1px solid var(--workbench-line, #dfe7ed);
  border-radius: 14px;
  background: #ffffff;
}

.settings-context-title {
  margin-bottom: 10px;
}

.settings-context-title h3 {
  margin: 0;
  color: var(--workbench-ink, #16202a);
  font-size: 14px;
}

.settings-context-list {
  display: grid;
  gap: 8px;
}

.settings-context-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--workbench-muted, #6b7684);
  font-size: 12px;
}

.settings-context-list strong {
  color: var(--workbench-ink, #16202a);
}

.settings-context-action {
  justify-content: center;
  height: 36px;
  margin-top: 8px;
  border-radius: 10px;
  background: #e8f2ff;
  color: var(--workbench-primary, #1d6fe8);
  font-size: 13px;
  font-weight: 800;
}

.settings-container {
  min-height: 100vh;
  background-color: var(--background-color);
  color: var(--text-color);
  padding-top: 46px;
  padding-bottom: 20px;
}

@media screen and (min-width: 901px) {
  .settings-container {
    min-height: 100%;
    padding-top: 0;
    padding-bottom: 0;
    background: transparent;
    overflow-y: auto;
  }

  .settings-container :deep(.van-nav-bar) {
    position: static;
  }
}

.settings-list {
  margin-top: 20px;
}

.popup-title {
  text-align: center;
  padding: 16px;
  font-size: 16px;
  font-weight: bold;
  border-bottom: 1px solid #eee;
}

.theme-list {
  display: flex;
  flex-wrap: wrap;
  padding: 16px;
}

.theme-item {
  width: 25%;
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 16px;
  cursor: pointer;
}

.theme-color {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  margin-bottom: 8px;
  border: 2px solid transparent;
}

.theme-item.active .theme-color {
  border-color: #1989fa;
}

.theme-name {
  font-size: 12px;
}

.popup-footer {
  padding: 16px;
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
}

.language-active {
  background-color: #f5f5f5;
}
</style>
