import { createRouter, createWebHistory } from 'vue-router'

// 1. Define the routing map with metadata for roles
const routes = [
  // Public Routes
  {
    path: '/',
    name: 'login-register',
    component: () => import('../views/auth/LoginRegisterView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/unauthorized',
    name: 'unauthorized',
    component: () => import('../views/UnauthorizedView.vue'),
    meta: { requiresAuth: false }
  },

  // Delegate Routes
  {
    path: '/delegate/dashboard',
    name: 'delegate-dashboard',
    component: () => import('../views/delegate/DelegateDashboardView.vue'),
    meta: { requiresAuth: true, role: 'delegate' }
  },

  // Advisor Routes
  {
    path: '/advisor/delegates',
    name: 'advisor-delegates',
    component: () => import('../views/advisor/DelegatesOverviewView.vue'),
    meta: { requiresAuth: true, role: 'advisor' }
  },
  {
    path: '/advisor/school-overview',
    name: 'advisor-school',
    component: () => import('../views/advisor/SchoolOverviewView.vue'),
    meta: { requiresAuth: true, role: 'advisor' }
  },

  // Chair Routes
  {
    path: '/chair/overview',
    name: 'chair-overview',
    component: () => import('../views/chair/CommitteeOverviewView.vue'),
    meta: { requiresAuth: true, role: 'chair' }
  },
  {
    path: '/chair/grading',
    name: 'chair-grading',
    component: () => import('../views/chair/PaperGradingView.vue'),
    meta: { requiresAuth: true, role: 'chair' }
  },
  {
    path: '/chair/awards',
    name: 'chair-awards',
    component: () => import('../views/chair/AwardsView.vue'),
    meta: { requiresAuth: true, role: 'chair' }
  },

  // Admin Routes
  {
    path: '/admin/dashboard',
    name: 'admin-dashboard',
    component: () => import('../views/admin/AdminDashboardView.vue'),
    meta: { requiresAuth: true, role: 'admin' }
  },

  // Catch-all 404 redirect (Send unknown URLs back to login/home)
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 2. The Gatekeeper: Role-Based Navigation Guard
router.beforeEach((to, from, next) => {
  // NOTE: Replace these placeholders with your actual authentication state management 
  // (like a Pinia store or a reactive state variable that tracks the logged-in user)
  const isLoggedIn = false // e.g., authStore.isAuthenticated
  const userRole = null     // e.g., authStore.user.role ('delegate', 'advisor', etc.)

  // Check if the target route requires authentication
  if (to.meta.requiresAuth) {
    if (!isLoggedIn) {
      // User is not logged in, boot them to the login/register view
      next({ name: 'login-register' })
    } else if (to.meta.role && to.meta.role !== userRole) {
      // User is logged in but doesn't have the correct clearance role
      next({ name: 'unauthorized' })
    } else {
      // Authorized. Let them through!
      next()
    }
  } else {
    // Public page. No checks needed.
    next()
  }
})

export default router