import { createRouter, createWebHistory } from 'vue-router'

// Layout Import
import AppLayout from '../layouts/AppLayout.vue'

const routes = [
  // PUBLIC ROUTES (No AppLayout wrapper)
  {
    path: '/',
    name: 'login-register',
    component: () => import('../views/auth/LoginRegisterView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/unauthorized',
    name: 'unauthorized',
    component: () => import('../views/errors/UnauthorizedView.vue'),
    meta: { requiresAuth: false }
  },

  // PROTECTED ROUTES (Wrapped inside AppLayout)
  {
    path: '/',
    component: AppLayout,
    meta: { requiresAuth: true },
    children: [
      // Delegate Routes
      {
        path: 'delegate/dashboard',
        name: 'delegate-dashboard',
        component: () => import('../views/delegate/DelegateDashboardView.vue'),
        // This page carries its own header (the intro platform), so the shell hides its navbar.
        meta: { roles: ['delegate'], hideNavbar: true }
      },

      // Advisor Routes
      // Landing redirects: the login screen used to push `/<role>/dashboard`, so these keep
      // that URL (and any bookmark of it) working instead of falling through to the 404.
      { path: 'advisor/dashboard', redirect: '/advisor/school-overview' },
      {
        path: 'advisor/delegates',
        name: 'advisor-delegates',
        component: () => import('../views/advisor/AdvisorDelegatesView.vue'),
        meta: { roles: ['advisor'] }
      },
      {
        path: 'advisor/school-overview',
        name: 'school-overview',
        component: () => import('../views/advisor/AdvisorSchoolView.vue'),
        meta: { roles: ['advisor'] }
      },

      // Chair Routes
      { path: 'chair/dashboard', redirect: '/chair/committee' },
      {
        path: 'chair/committee',
        name: 'chair-committee',
        component: () => import('../views/chair/ChairCommitteeView.vue'),
        meta: { roles: ['chair', 'admin'] }
      },
      {
        path: 'chair/grading',
        name: 'chair-grading',
        component: () => import('../views/chair/ChairGradingView.vue'),
        meta: { roles: ['chair', 'admin'] }
      },
      {
        path: 'chair/awards',
        name: 'chair-awards',
        component: () => import('../views/chair/ChairAwardsView.vue'),
        meta: { roles: ['chair', 'admin'] }
      },

      // Admin Routes
      {
        path: 'admin/dashboard',
        name: 'admin-dashboard',
        component: () => import('../views/admin/AdminDashboardView.vue'),
        meta: { roles: ['admin'] }
      }
    ]
  },

  // Catch-all 404 Error View
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('../views/errors/NotFoundView.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Helper function to map role to home route.
// Exported because the login screen redirects with it: `/advisor/dashboard` and
// `/chair/dashboard` are not routes, so building the path from the role name sent those two
// roles to the 404 page.
export const getHomeRouteForRole = (role) => {
  switch (role) {
    case 'delegate': return '/delegate/dashboard'
    // The school overview is the advisor's landing page: it is where the conference
    // checklist and billing live, which is what they open the app for.
    case 'advisor': return '/advisor/school-overview'
    case 'chair': return '/chair/committee'
    case 'admin': return '/admin/dashboard'
    default: return '/'
  }
}

import { useAuthStore } from '../stores/auth.js'

// Global Navigation Guard
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  const isLoggedIn = authStore.isLoggedIn
  const userRole = authStore.userRole

  // 1. If logged in and navigating to login page, send to home
  if (to.name === 'login-register' && isLoggedIn) {
    return next(getHomeRouteForRole(userRole))
  }

  // 2. Auth Check
  if (to.meta.requiresAuth) {
    if (!isLoggedIn) {
      return next({ name: 'login-register' })
    }

    // 3. Role Authorization Check
    const allowedRoles = to.meta.roles
    if (allowedRoles && !allowedRoles.includes(userRole)) {
      return next({ name: 'unauthorized' })
    }
  }

  next()
})

export default router