import { Request, Response } from 'express';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { LoginRequest, RegisterRequest } from '../types/index.js';
import { mockUsers } from '../utils/mockData';

// Use mock users for development (In production, use a real database)
const users: Array<{
  id: string;
  username: string;
  email: string;
  password: string;
  role: 'admin' | 'user';
}> = mockUsers as any[];

// Initialize admin user
const initializeAdminUser = async () => {
  const adminUser = users.find(u => u.username === 'admin');
  if (adminUser && !adminUser.password) {
    const hashedPassword = await bcrypt.hash(process.env.ADMIN_PASSWORD || 'changeme', 10);
    adminUser.password = hashedPassword;
    console.log('✓ Admin user initialized: admin/changeme (10GB test quota)');
  } else if (!adminUser) {
    const hashedPassword = await bcrypt.hash(process.env.ADMIN_PASSWORD || 'changeme', 10);
    users.push({
      id: '1',
      username: process.env.ADMIN_USERNAME || 'admin',
      email: process.env.ADMIN_EMAIL || 'admin@localhost',
      password: hashedPassword,
      role: 'admin'
    });
  }
};

initializeAdminUser();

export const register = async (req: Request, res: Response): Promise<void> => {
  try {
    const { username, email, password }: RegisterRequest = req.body;

    if (!username || !email || !password) {
      res.status(400).json({ error: 'All fields are required' });
      return;
    }

    const existingUser = users.find(u => u.username === username || u.email === email);
    if (existingUser) {
      res.status(409).json({ error: 'User already exists' });
      return;
    }

    const hashedPassword = await bcrypt.hash(password, 10);
    const newUser = {
      id: String(users.length + 1),
      username,
      email,
      password: hashedPassword,
      role: 'user' as const
    };

    users.push(newUser);

    const jwtSecret = process.env.JWT_SECRET || 'secret';
    const jwtExpiry = process.env.JWT_EXPIRES_IN || '7d';
    const token = jwt.sign(
      { userId: newUser.id, username: newUser.username, role: newUser.role },
      jwtSecret,
      { expiresIn: jwtExpiry } as jwt.SignOptions
    );

    res.status(201).json({
      token,
      user: {
        id: newUser.id,
        username: newUser.username,
        email: newUser.email,
        role: newUser.role
      }
    });
  } catch (error) {
    res.status(500).json({ error: 'Registration failed' });
  }
};

export const login = async (req: Request, res: Response): Promise<void> => {
  try {
    const { username, password }: LoginRequest = req.body;

    if (!username || !password) {
      res.status(400).json({ error: 'Username and password are required' });
      return;
    }

    const user = users.find(u => u.username === username);
    if (!user) {
      res.status(401).json({ error: 'Invalid credentials' });
      return;
    }

    const isValidPassword = await bcrypt.compare(password, user.password);
    if (!isValidPassword) {
      res.status(401).json({ error: 'Invalid credentials' });
      return;
    }

    const jwtSecret = process.env.JWT_SECRET || 'secret';
    const jwtExpiry = process.env.JWT_EXPIRES_IN || '7d';
    const token = jwt.sign(
      { userId: user.id, username: user.username, role: user.role },
      jwtSecret,
      { expiresIn: jwtExpiry } as jwt.SignOptions
    );

    res.json({
      token,
      user: {
        id: user.id,
        username: user.username,
        email: user.email,
        role: user.role
      }
    });
  } catch (error) {
    res.status(500).json({ error: 'Login failed' });
  }
};

export const logout = (_req: Request, res: Response): void => {
  res.json({ message: 'Logged out successfully' });
};
