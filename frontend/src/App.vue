<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppConfigStore } from '@/stores/appConfig'
import DemoBanner from '@/components/DemoBanner.vue'

const auth = useAuthStore()
const appConfig = useAppConfigStore()
const route = useRoute()
// The demo's login panel explains itself; every page after it carries the banner.
const showBanner = computed(() => appConfig.demo && route.name && route.name !== 'login')
onMounted(() => auth.init())
</script>

<template>
  <DemoBanner v-if="showBanner" />
  <RouterView v-slot="{ Component }">
    <Transition
      name="fade"
      mode="out-in"
    >
      <component :is="Component" />
    </Transition>
  </RouterView>
</template>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 120ms ease-out;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
