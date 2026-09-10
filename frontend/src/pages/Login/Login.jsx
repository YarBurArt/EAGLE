import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/shared/api/axios'

export const Login = () => {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [err, setErr] = useState('')
    const navigate = useNavigate()

    const handleSubmit = async (e) => {
        e.preventDefault()
        setErr('')
        try {
            const body = new URLSearchParams({ username: email, password, })
            const { data } = await api.post('/auth/access-token', body, {
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
            })
            // FIXME: possible CWE-922 for case CWE-79
            localStorage.setItem('access_token', data.access_token)
            localStorage.setItem('refresh_token', data.refresh_token)
            
            navigate('/', { replace: true })
        } catch (err) {
            const detail = err.response?.data?.detail

            if (Array.isArray(detail)) {
                setErr(detail.map((e) => e.msg).join(', '))
            } else {
                setErr(detail || 'Login failed, sorry')
            }
        }
    }

    return (
    <div className="flex justify-center bg-bg-app mt-16">
    <form 
        onSubmit={handleSubmit} 
        id='loginForm' 
        className='w-120 bg-bg-card border border-border-subtle rounded-md p-4 flex flex-col gap-4'
    >
        <h2 className="text-lg font-bold text-text-primary tracking-wider">EAGLE Login</h2>
        
        <label className="text-xs text-text-muted text-left">Email</label>
        <input 
            type="email" 
            id="email" 
            value={email}
            onChange={(e) => setEmail(e.target.value)} 
            placeholder='Registered email' 
            required
            className='w-full px-3 py-2 bg-bg-input border border-border-default rounded text-sm text-text-primary outline-none focus:border-accent transition-colors'
        />
        
        <label className="text-xs text-text-muted text-left">Password</label>
        <input 
            type="password" 
            id="password" 
            value={password} 
            onChange={(e) => setPassword(e.target.value)}
            placeholder='Super_secret_password' 
            required
            className='w-full px-3 py-2 bg-bg-input border border-border-default rounded text-sm text-text-primary outline-none focus:border-accent transition-colors'
        />
        
        <button 
            type="submit"
            className='w-full py-2 bg-accent text-white text-sm font-medium rounded hover:opacity-90 transition-opacity'
        >
        Sign in
        </button>
        <p>An account can be created by admin</p>
        {err && <p className="text-xs text-danger">{err}</p>}
    </form>
    </div>
    )
}