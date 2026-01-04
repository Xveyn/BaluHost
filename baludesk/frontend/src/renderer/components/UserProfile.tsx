import React, { useState, useEffect } from 'react';
import { User, Upload, Camera } from 'lucide-react';

interface UserProfile {
  id: string;
  username: string;
  email?: string;
  avatar_url?: string;
}

interface UserProfileProps {
  user?: UserProfile;
  serverUrl: string;
  onAvatarChange?: (avatarUrl: string) => void;
}

const UserProfile: React.FC<UserProfileProps> = ({
  user,
  serverUrl,
  onAvatarChange,
}) => {
  const [profile, setProfile] = useState<UserProfile | null>(user || null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(
    user?.avatar_url ? `${serverUrl}${user.avatar_url}` : null
  );
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);

  // Fetch full user profile from backend
  useEffect(() => {
    const fetchUserProfile = async () => {
      if (!user?.id) return;
      
      try {
        const token = sessionStorage.getItem('auth_token');
        const response = await fetch(`${serverUrl}/api/users/${user.id}`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (response.ok) {
          const data = await response.json();
          setProfile(data);
          if (data.avatar_url) {
            setAvatarPreview(`${serverUrl}${data.avatar_url}`);
          }
        }
      } catch (error) {
        console.error('Failed to fetch user profile:', error);
      }
    };

    fetchUserProfile();
  }, [user?.id, serverUrl]);

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      setMessage({ type: 'error', text: 'Please select an image file' });
      return;
    }

    // Validate file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      setMessage({ type: 'error', text: 'File size must be less than 5MB' });
      return;
    }

    setAvatarFile(file);

    // Show preview
    const reader = new FileReader();
    reader.onload = (event) => {
      setAvatarPreview(event.target?.result as string);
    };
    reader.readAsDataURL(file);
  };

  const handleAvatarUpload = async () => {
    if (!avatarFile || !profile) return;

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('avatar', avatarFile);

      const token = sessionStorage.getItem('auth_token');
      const response = await fetch(
        `${serverUrl}/api/users/${profile.id}/avatar`,
        {
          method: 'POST',
          body: formData,
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to upload avatar');
      }

      const data = await response.json();
      const newAvatarUrl = `${serverUrl}${data.avatar_url}`;
      setProfile({ ...profile, avatar_url: data.avatar_url });
      setAvatarPreview(newAvatarUrl);
      setAvatarFile(null);
      setMessage({ type: 'success', text: 'Avatar updated successfully!' });

      if (onAvatarChange) {
        onAvatarChange(newAvatarUrl);
      }

      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      console.error('Avatar upload error:', error);
      setMessage({ type: 'error', text: 'Failed to upload avatar' });
    } finally {
      setUploading(false);
    }
  };

  if (!profile) {
    return (
      <div className="flex items-center justify-center p-8 text-slate-400">
        Loading user profile...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-semibold mb-2">User Profile</h2>
          <p className="text-sm text-slate-400">Manage your profile information</p>
        </div>
      </div>

      {/* Message */}
      {message && (
        <div
          className={`rounded-lg p-4 text-sm ${
            message.type === 'success'
              ? 'bg-green-500/20 text-green-400'
              : 'bg-red-500/20 text-red-400'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Avatar Section */}
      <div className="bg-slate-800 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center space-x-2">
          <Camera className="h-5 w-5" />
          <span>Avatar</span>
        </h3>

        <div className="flex items-center space-x-6">
          {/* Avatar Display */}
          <div className="flex-shrink-0">
            {avatarPreview ? (
              <img
                src={avatarPreview}
                alt={profile.username}
                className="h-32 w-32 rounded-full object-cover border-4 border-slate-700"
                onError={() => setAvatarPreview(null)}
              />
            ) : (
              <div className="h-32 w-32 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center border-4 border-slate-700">
                <User className="h-12 w-12 text-white" />
              </div>
            )}
          </div>

          {/* Upload Controls */}
          <div className="flex-1">
            <div className="space-y-3">
              <div>
                <label
                  htmlFor="avatar-input"
                  className="inline-flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg cursor-pointer transition-colors"
                >
                  <Upload className="h-4 w-4" />
                  <span>Choose Image</span>
                </label>
                <input
                  id="avatar-input"
                  type="file"
                  accept="image/*"
                  onChange={handleAvatarChange}
                  className="hidden"
                />
              </div>

              {avatarFile && (
                <div className="space-y-2">
                  <p className="text-sm text-slate-400">
                    Selected: {avatarFile.name}
                  </p>
                  <button
                    onClick={handleAvatarUpload}
                    disabled={uploading}
                    className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
                  >
                    {uploading ? 'Uploading...' : 'Upload Avatar'}
                  </button>
                </div>
              )}

              <p className="text-xs text-slate-500">
                PNG, JPG, GIF or WebP (max 5MB)
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Profile Info */}
      <div className="bg-slate-800 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">Profile Information</h3>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Username
            </label>
            <p className="text-white">{profile.username}</p>
          </div>

          {profile.email && (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Email
              </label>
              <p className="text-white">{profile.email}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default UserProfile;
