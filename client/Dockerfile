# ===================================
# Stage 1: Builder
# ===================================
FROM node:18-alpine AS builder

# Set working directory
WORKDIR /build

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci --omit=dev --ignore-scripts

# Copy application source
COPY . .

# Build the application
# This runs TypeScript compiler and Vite build
RUN npm run build

# ===================================
# Stage 2: Runtime (Nginx)
# ===================================
FROM nginx:alpine AS runtime

# Install curl for health checks
RUN apk add --no-cache curl

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/baluhost.conf

# Copy built assets from builder stage
COPY --from=builder /build/dist /usr/share/nginx/html

# Create nginx user and set permissions
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    chmod -R 755 /var/cache/nginx

# Switch to non-root user
USER nginx

# Expose port 80
EXPOSE 80

# Health check
# Checks if nginx is serving the index.html
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/ || exit 1

# Start nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
