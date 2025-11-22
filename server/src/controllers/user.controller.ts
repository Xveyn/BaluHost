import { Request, Response } from 'express';

// Mock user database
const users = [
  { id: '1', username: 'admin', email: 'admin@localhost', role: 'admin' }
];

export const getAllUsers = (_req: Request, res: Response): void => {
  const safeUsers = users.map(({ id, username, email, role }) => ({
    id,
    username,
    email,
    role
  }));
  res.json({ users: safeUsers });
};

export const createUser = (req: Request, res: Response): void => {
  const { username, email, role } = req.body;
  
  if (!username || !email) {
    res.status(400).json({ error: 'Username and email are required' });
    return;
  }

  const newUser = {
    id: String(users.length + 1),
    username,
    email,
    role: role || 'user'
  };

  users.push(newUser);
  res.status(201).json({ user: newUser });
};

export const updateUser = (req: Request, res: Response): void => {
  const { id } = req.params;
  const { username, email, role } = req.body;

  const userIndex = users.findIndex(u => u.id === id);
  if (userIndex === -1) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  if (username) users[userIndex].username = username;
  if (email) users[userIndex].email = email;
  if (role) users[userIndex].role = role;

  res.json({ user: users[userIndex] });
};

export const deleteUser = (req: Request, res: Response): void => {
  const { id } = req.params;

  const userIndex = users.findIndex(u => u.id === id);
  if (userIndex === -1) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  users.splice(userIndex, 1);
  res.json({ message: 'User deleted successfully' });
};
