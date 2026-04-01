# SaaS Implementation Plan

## Current Status

✅ **Phase 1 Complete**: Core manga automation system working
- Queue-based chapter posting system
- Remotion video generation with effects
- Viral caption and hashtag generation
- Manual chapter selection via webhook
- All workflows tested and validated

## Phase 2: SaaS Transformation

### Goal
Transform the manga automation platform into an enterprise-grade multi-tenant SaaS with:
- Multi-user authentication and organization workspaces
- TikTok multi-account management with proxy support
- N8N workflow dashboard and monitoring
- Analytics and performance tracking
- Smart content scheduling calendar
- A/B testing capabilities

---

## Architecture Overview

### 1. Multi-Tenancy Layer
- User authentication (Supabase Auth or Clerk)
- Organization-based data isolation
- Role-based access control (Owner, Admin, Member)

### 2. Proxy Management
- Proxy pool for TikTok accounts
- Automatic proxy rotation
- Health monitoring and failover

### 3. Workflow Orchestration
- N8N workflow execution tracking
- Real-time status updates
- Manual workflow triggers from dashboard

### 4. Analytics Engine
- Post-upload engagement tracking
- A/B test result analysis
- Performance metrics and trends

### 5. Smart Scheduling
- Visual content calendar
- Drag-and-drop scheduling
- Optimal posting time suggestions

---

## Implementation Tasks


### Phase 2.1: Database Schema Extensions (Multi-Tenancy)

**Priority**: HIGH | **Estimated Time**: 2-3 hours

#### Tasks:
1. Create `users` table
   - id, email, password_hash, name, created_at
   - Integration with Supabase Auth

2. Create `organizations` table
   - id, name, slug, owner_id, plan_tier, created_at
   - Subscription and billing info

3. Create `organization_members` table
   - organization_id, user_id, role (owner/admin/member)
   - Permissions and access control

4. Add `organization_id` to existing tables:
   - manga, tiktok_accounts, videos, manga_chapters
   - Add indexes for performance

5. Create `proxies` table
   - id, organization_id, host, port, username, password
   - protocol (http/https/socks5), is_active, last_checked

6. Add `proxy_id` to `tiktok_accounts` table

#### Migration Script:
```sql
-- Create migration: 004_multi_tenancy.sql
```

#### Verification:
- Run migration on local Docker postgres
- Verify all foreign keys and indexes
- Test data isolation queries

---

### Phase 2.2: Workflow Tracking System

**Priority**: HIGH | **Estimated Time**: 3-4 hours

#### Tasks:
1. Create `workflow_executions` table
   - id, organization_id, workflow_name, status
   - started_at, completed_at, error_message

2. Create `workflow_steps` table
   - id, execution_id, step_name, status
   - started_at, completed_at, output_data

3. Add API endpoints in `server.ts`:
   - `GET /api/workflows` - List all workflows
   - `POST /api/workflows/:id/run` - Trigger workflow
   - `POST /api/workflows/log-step` - Log step completion
   - `GET /api/workflows/executions` - Get execution history

4. Update N8N workflows to log steps:
   - Add HTTP Request nodes after each major step
   - POST to `/api/workflows/log-step` with status

#### Verification:
- Trigger workflow from dashboard
- Verify steps logged in database
- Check real-time status updates

---


### Phase 2.3: TikTok Multi-Account & Proxy Management

**Priority**: HIGH | **Estimated Time**: 4-5 hours

#### Tasks:
1. Backend API endpoints:
   - `GET /api/tiktok-accounts` - List accounts with proxy info
   - `POST /api/tiktok-accounts` - Create account with proxy assignment
   - `PUT /api/tiktok-accounts/:id` - Update account/proxy
   - `DELETE /api/tiktok-accounts/:id` - Remove account
   - `GET /api/proxies` - List available proxies
   - `POST /api/proxies` - Add new proxy
   - `POST /api/proxies/:id/test` - Test proxy connection

2. Update `upload_tiktok.py`:
   - Load proxy from database for account
   - Configure Playwright to use proxy
   - Handle proxy failures with retry logic
   - Log proxy usage and errors

3. Proxy health monitoring:
   - Create `check_proxy_health.py` script
   - Test each proxy periodically
   - Update `is_active` status in database
   - Alert on proxy failures

#### Code Example:
```python
# upload_tiktok.py
def get_account_proxy(account_id):
    result = db.query(
        "SELECT p.* FROM proxies p "
        "JOIN tiktok_accounts ta ON ta.proxy_id = p.id "
        "WHERE ta.id = %s AND p.is_active = true",
        [account_id]
    )
    return result[0] if result else None

def upload_with_proxy(video_path, account_id):
    proxy = get_account_proxy(account_id)
    
    browser_args = {}
    if proxy:
        browser_args['proxy'] = {
            'server': f'{proxy.protocol}://{proxy.host}:{proxy.port}',
            'username': proxy.username,
            'password': proxy.password
        }
    
    browser = playwright.chromium.launch(**browser_args)
    # ... rest of upload logic
```

#### Verification:
- Add proxy via API
- Assign to TikTok account
- Upload video and verify proxy used
- Check logs for proxy connection

---


### Phase 2.4: Dashboard - Authentication & Routing

**Priority**: HIGH | **Estimated Time**: 3-4 hours

#### Tasks:
1. Install dependencies:
   ```bash
   cd dashboard
   npm install @supabase/supabase-js react-router-dom
   ```

2. Setup Supabase Auth:
   - Create Supabase project (or use existing)
   - Configure auth providers (email/password, Google, etc.)
   - Add environment variables to dashboard

3. Create auth context and provider:
   - `src/contexts/AuthContext.tsx`
   - Login, logout, signup functions
   - User session management

4. Update `App.tsx`:
   - Add React Router
   - Protected routes for authenticated users
   - Redirect to login if not authenticated

5. Create auth pages:
   - `src/pages/Login.tsx`
   - `src/pages/Signup.tsx`
   - `src/pages/ForgotPassword.tsx`

#### Code Structure:
```typescript
// src/contexts/AuthContext.tsx
export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // Auth functions
  const login = async (email, password) => { ... };
  const signup = async (email, password) => { ... };
  const logout = async () => { ... };
  
  return (
    <AuthContext.Provider value={{ user, login, signup, logout }}>
      {!loading && children}
    </AuthContext.Provider>
  );
};
```

#### Verification:
- Sign up new user
- Login and verify session
- Access protected routes
- Logout and verify redirect

---


### Phase 2.5: Dashboard - Workflow Management Page

**Priority**: MEDIUM | **Estimated Time**: 4-5 hours

#### Tasks:
1. Create `src/pages/Workflows.tsx`:
   - List all available workflows
   - Show execution history
   - Real-time status updates
   - Manual trigger buttons

2. Create workflow components:
   - `WorkflowCard.tsx` - Display workflow info
   - `ExecutionTimeline.tsx` - Show step progress
   - `WorkflowTrigger.tsx` - Manual trigger form

3. Implement real-time updates:
   - Poll `/api/workflows/executions` every 5 seconds
   - Or use WebSocket for live updates
   - Show progress bars for running workflows

4. Add workflow filtering:
   - Filter by status (running, completed, failed)
   - Filter by workflow type
   - Search by execution ID

#### UI Features:
- Workflow cards with status badges
- Execution timeline with step details
- Error logs for failed workflows
- Retry button for failed executions
- Manual trigger with parameter inputs

#### Verification:
- View workflow list
- Trigger workflow manually
- Watch real-time progress
- View execution history
- Check error details for failures

---

### Phase 2.6: Dashboard - TikTok Accounts Page

**Priority**: MEDIUM | **Estimated Time**: 3-4 hours

#### Tasks:
1. Create `src/pages/TikTokAccounts.tsx`:
   - List all TikTok accounts
   - Show account status and metrics
   - Shadow ban indicators
   - Proxy assignments

2. Create account components:
   - `AccountCard.tsx` - Display account info
   - `AccountForm.tsx` - Add/edit account
   - `ProxySelector.tsx` - Assign proxy to account

3. Add account management:
   - Add new account with credentials
   - Edit account settings
   - Delete account
   - Test account connection

4. Show account metrics:
   - Total posts
   - Last post date
   - Upload success rate
   - Shadow ban status

#### UI Features:
- Account cards with status indicators
- Proxy assignment dropdown
- Shadow ban warning badges
- Account health score
- Quick actions (test, edit, delete)

#### Verification:
- Add new TikTok account
- Assign proxy to account
- View account metrics
- Test account connection
- Check shadow ban detection

---


### Phase 2.7: Dashboard - Content Calendar

**Priority**: MEDIUM | **Estimated Time**: 5-6 hours

#### Tasks:
1. Install calendar library:
   ```bash
   npm install react-big-calendar date-fns
   ```

2. Create `src/pages/ContentCalendar.tsx`:
   - Display videos on calendar
   - Drag-and-drop to reschedule
   - Color-coded by status
   - Month/week/day views

3. Add scheduling logic:
   - Update `scheduled_for` in videos table
   - Respect optimal posting times
   - Prevent scheduling conflicts
   - Batch scheduling support

4. Create calendar components:
   - `CalendarView.tsx` - Main calendar display
   - `VideoEvent.tsx` - Video card on calendar
   - `ScheduleModal.tsx` - Edit schedule details

5. Add scheduling features:
   - Optimal time suggestions
   - Bulk scheduling
   - Recurring schedules
   - Time zone support

#### Code Example:
```typescript
// ContentCalendar.tsx
const events = videos.map(video => ({
  id: video.id,
  title: video.manga_title,
  start: new Date(video.scheduled_for),
  end: new Date(video.scheduled_for),
  resource: video
}));

const handleEventDrop = async ({ event, start }) => {
  await fetch(`/api/videos/${event.id}/schedule`, {
    method: 'PUT',
    body: JSON.stringify({ scheduled_for: start })
  });
};
```

#### Verification:
- View videos on calendar
- Drag video to new date
- Verify database updated
- Check optimal time suggestions
- Test bulk scheduling

---


### Phase 2.8: Analytics & Performance Tracking

**Priority**: MEDIUM | **Estimated Time**: 6-7 hours

#### Tasks:
1. Create `fetch_tiktok_stats.py`:
   - Scrape view/like/comment counts
   - Store in `video_analytics` table
   - Run periodically (every 6 hours)
   - Handle rate limiting

2. Add analytics API endpoints:
   - `GET /api/analytics/overview` - Dashboard metrics
   - `GET /api/analytics/videos/:id` - Video performance
   - `GET /api/analytics/trends` - Growth trends
   - `GET /api/analytics/ab-tests` - A/B test results

3. Create `src/pages/Analytics.tsx`:
   - Overview dashboard with key metrics
   - Performance charts (Recharts)
   - Video comparison
   - A/B test results

4. Install chart library:
   ```bash
   npm install recharts
   ```

5. Create analytics components:
   - `MetricsCard.tsx` - KPI cards
   - `PerformanceChart.tsx` - Line/bar charts
   - `VideoComparison.tsx` - Side-by-side comparison
   - `ABTestResults.tsx` - Test winner display

#### Metrics to Track:
- Total views, likes, comments, shares
- Engagement rate (likes/views)
- Follower growth
- Best performing content
- Optimal posting times
- Hashtag performance
- A/B test winners

#### Code Example:
```python
# fetch_tiktok_stats.py
def scrape_video_stats(video_url):
    # Use Playwright to scrape TikTok
    page.goto(video_url)
    views = page.locator('[data-e2e="video-views"]').text_content()
    likes = page.locator('[data-e2e="like-count"]').text_content()
    
    return {
        'views': parse_count(views),
        'likes': parse_count(likes),
        'comments': parse_count(comments),
        'shares': parse_count(shares)
    }
```

#### Verification:
- Run stats scraper manually
- Verify data in database
- View analytics dashboard
- Check chart rendering
- Compare video performance

---


### Phase 2.9: A/B Testing System

**Priority**: LOW | **Estimated Time**: 4-5 hours

#### Tasks:
1. Update caption generation to create variants:
   - Generate 2-3 caption variations per video
   - Different formulas and emojis
   - Store variants in database

2. Create `video_variants` table:
   - id, video_id, variant_type (caption/thumbnail)
   - variant_data (JSON), performance_score

3. Add A/B test logic:
   - Randomly select variant for upload
   - Track which variant was used
   - Compare performance after 24 hours
   - Identify winning variants

4. Update dashboard analytics:
   - Show A/B test results
   - Highlight winning formulas
   - Suggest best practices

#### Code Example:
```typescript
// Generate caption variants
const variants = [
  await captionGenerator.generateCaption({ formulaType: 'emotional_hook' }),
  await captionGenerator.generateCaption({ formulaType: 'question' }),
  await captionGenerator.generateCaption({ formulaType: 'recommendation' })
];

// Store variants
for (const variant of variants) {
  await db.query(
    'INSERT INTO video_variants (video_id, variant_type, variant_data) VALUES ($1, $2, $3)',
    [videoId, 'caption', JSON.stringify(variant)]
  );
}

// Select random variant for upload
const selectedVariant = variants[Math.floor(Math.random() * variants.length)];
```

#### Verification:
- Generate video with variants
- Upload with random variant
- Track performance
- View A/B test results
- Identify winning formula

---


### Phase 2.10: Notifications & Alerts

**Priority**: LOW | **Estimated Time**: 2-3 hours

#### Tasks:
1. Create notification system:
   - Email alerts for failures
   - Shadow ban detection alerts
   - Low proxy health warnings
   - Daily performance summary

2. Add notification preferences:
   - User settings for alert types
   - Email/SMS/webhook options
   - Alert frequency settings

3. Implement alert triggers:
   - Upload failure (3+ consecutive)
   - Shadow ban detected
   - Proxy connection failed
   - Workflow execution failed
   - Daily summary at 9 AM

4. Create notification templates:
   - Email templates for each alert type
   - Include actionable information
   - Link to dashboard for details

#### Verification:
- Trigger test alert
- Verify email received
- Check alert preferences
- Test different alert types

---

## Implementation Timeline

### Week 1: Foundation
- Day 1-2: Multi-tenancy database schema
- Day 3-4: Workflow tracking system
- Day 5: TikTok proxy management backend

### Week 2: Dashboard Core
- Day 1-2: Authentication & routing
- Day 3-4: Workflow management page
- Day 5: TikTok accounts page

### Week 3: Advanced Features
- Day 1-3: Content calendar
- Day 4-5: Analytics dashboard

### Week 4: Polish & Testing
- Day 1-2: A/B testing system
- Day 3: Notifications
- Day 4-5: Integration testing & bug fixes

---

## Success Criteria

### Phase 2 Complete When:
- ✅ Multi-user authentication working
- ✅ Organization data isolation verified
- ✅ Proxy-based TikTok uploads working
- ✅ Workflow dashboard showing real-time status
- ✅ Content calendar with drag-and-drop
- ✅ Analytics showing engagement metrics
- ✅ A/B testing generating and tracking variants
- ✅ Notifications alerting on failures

---

## Next Steps

1. **Review this plan** - Confirm scope and priorities
2. **Set up Supabase** - Create project for auth
3. **Start with Phase 2.1** - Database schema extensions
4. **Incremental testing** - Test each phase before moving on
5. **Deploy to staging** - Test full system before production

---

## Questions to Address

1. **Auth Provider**: Supabase Auth or Clerk? (Recommend Supabase for simplicity)
2. **Proxy Provider**: Which proxy service to integrate? (Recommend Bright Data or Smartproxy)
3. **Notification Service**: SendGrid, AWS SES, or other?
4. **Deployment**: Docker Compose, Kubernetes, or managed services?
5. **Monitoring**: Sentry, LogRocket, or custom solution?

---

## Resources Needed

- Supabase account (free tier sufficient for testing)
- Proxy service account (for TikTok uploads)
- Email service account (for notifications)
- Domain name (for production deployment)
- SSL certificates (Let's Encrypt)

