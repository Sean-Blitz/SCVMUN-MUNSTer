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
        meta: { roles: ['delegate'] }
      },

      // Advisor Routes
      {
        path: 'advisor/delegates',
        name: 'advisor-delegates',
        component: () => import('../views/advisor/AdvisorDelegatesView.vue'),
        meta: { roles: ['advisor'] }
      },
      {
        path: 'advisor/school-overview',
        name: 'advisor-school',
        component: () => import('../views/advisor/AdvisorSchoolView.vue'),
        meta: { roles: ['advisor'] }
      },

      // Chair Routes
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

// Helper function to map role to home route
const getHomeRouteForRole = (role) => {
  switch (role) {
    case 'delegate': return '/delegate/dashboard'
    case 'advisor': return '/advisor/delegates'
    case 'chair': return '/chair/committee'
    case 'admin': return '/admin/dashboard'
    default: return '/'
  }
}

// Global Navigation Guard
router.beforeEach((to, from, next) => {
  // Replace these with your global state/Pinia store
  const isLoggedIn = false 
  const userRole = null    

  // 1. If user is logged in and tries to access Login page, send them to their dashboard
  if (to.name === 'login-register' && isLoggedIn) {
    return next(getHomeRouteForRole(userRole))
  }

  // 2. Route Requires Auth Check
  if (to.meta.requiresAuth) {
    if (!isLoggedIn) {
      // Unauthenticated -> Redirect to Login
      return next({ name: 'login-register' })
    }

    // 3. Role Authorization Check
    const allowedRoles = to.meta.roles
    if (allowedRoles && !allowedRoles.includes(userRole)) {
      // User lacks role access -> Redirect to 403
      return next({ name: 'unauthorized' })
    }
  }

  // Allow access
  next()
})

export default router