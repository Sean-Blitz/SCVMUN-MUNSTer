import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

// Optional: Import your global CSS styling (like Tailwind CSS) if you use it
// import './assets/main.css'

// 1. Initialize the Vue application instance using the root component (App.vue)
const app = createApp(App)

// 2. Install your plugins (like the router we built)
app.use(router)

// 3. Mount the application to the physical HTML file
// This tells Vue to take over the <div id="app"></div> inside your public/index.html
app.mount('#app')