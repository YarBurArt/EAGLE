import { createBrowserRouter } from 'react-router-dom'
import { Login } from '@/pages/Login/Login'

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/',
    element: (
      <>
        <p>
          Imagine cool Unified Kill Chain managment UI here <br />
          I'm just lazy, for now go to /api/docs like
        </p>
        <a href="http://127.1:8000/api/docs">http://127.1:8000/api/docs</a>
      </>
    ),
  },
])
