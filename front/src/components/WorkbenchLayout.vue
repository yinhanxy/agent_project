<template>
  <div class="workbench-layout" :class="[pageClass, { 'workbench-layout--single': singleContent }]">
    <slot name="rail">
      <desktop-rail />
    </slot>

    <aside class="workbench-sidebar" :aria-label="sidebarLabel">
      <slot name="sidebar" />
    </aside>

    <main class="workbench-main">
      <slot />
    </main>

    <aside class="workbench-context" :aria-label="contextLabel">
      <slot name="context" />
    </aside>

    <div class="workbench-mobile">
      <slot name="mobile">
        <slot />
      </slot>
    </div>
  </div>
</template>

<script setup>
import DesktopRail from './DesktopRail.vue';

defineProps({
  pageClass: {
    type: String,
    default: ''
  },
  sidebarLabel: {
    type: String,
    default: '栏目导航'
  },
  contextLabel: {
    type: String,
    default: '上下文信息'
  },
  singleContent: {
    type: Boolean,
    default: false
  }
});
</script>

<style scoped>
.workbench-layout {
  --workbench-bg: #f5f7f8;
  --workbench-surface: #ffffff;
  --workbench-soft: #f7fafc;
  --workbench-ink: #16202a;
  --workbench-muted: #6b7684;
  --workbench-line: #dfe7ed;
  --workbench-primary: #1d6fe8;
  --workbench-teal: #178c83;
  --workbench-shadow: 0 18px 50px rgba(20, 42, 68, 0.1);

  display: grid;
  grid-template-columns: 76px minmax(260px, 320px) minmax(0, 1fr) minmax(260px, 300px);
  width: 100vw;
  height: 100dvh;
  min-height: 100vh;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(238, 243, 247, 0.9)),
    radial-gradient(circle at 36% 0%, rgba(29, 111, 232, 0.13), transparent 34%),
    var(--workbench-bg);
  color: var(--workbench-ink);
  overflow: hidden;
}

.workbench-sidebar,
.workbench-context,
.workbench-main {
  min-height: 0;
}

.workbench-sidebar {
  overflow: hidden;
  padding: 18px 14px;
  border-right: 1px solid var(--workbench-line);
  background: rgba(250, 252, 254, 0.92);
}

.workbench-main {
  overflow: hidden;
}

.workbench-context {
  overflow-y: auto;
  padding: 18px 16px;
  border-left: 1px solid var(--workbench-line);
  background: rgba(255, 255, 255, 0.76);
}

.workbench-mobile {
  display: none;
}

@media screen and (max-width: 1180px) {
  .workbench-layout {
    grid-template-columns: 72px minmax(250px, 300px) minmax(0, 1fr);
  }

  .workbench-context {
    display: none;
  }
}

@media screen and (max-width: 900px) {
  .workbench-layout {
    display: block;
    width: 100%;
    height: auto;
    min-height: 100dvh;
    overflow: visible;
    background: transparent;
  }

  .workbench-sidebar,
  .workbench-main,
  .workbench-context {
    display: none;
  }

  .workbench-layout--single .workbench-main {
    display: block;
    overflow: visible;
  }

  .workbench-mobile {
    display: block;
  }

  .workbench-layout--single .workbench-mobile {
    display: none;
  }
}
</style>
