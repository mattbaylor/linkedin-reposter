"""Admin dashboard HTML templates and helpers."""

def get_dashboard_html(posts_data: list, stats: dict, settings) -> str:
    """Generate admin dashboard HTML."""
    
    # Build posts HTML
    posts_html = ""
    for post in posts_data:
        status_color = {
            "awaiting_approval": "#ffc107",
            "approved": "#28a745",
            "rejected": "#dc3545",
            "posted": "#17a2b8",
            "failed": "#dc3545"
        }.get(post['status'], "#6c757d")
        
        variants_html = ""
        for i, variant in enumerate(post.get('variants', []), 1):
            variant_status_badge = {
                "pending": "⏳ Pending",
                "approved": "✅ Approved",
                "rejected": "❌ Rejected",
                "posted": "📤 Posted"
            }.get(variant['status'], variant['status'])
            
            variants_html += f"""
            <div class="variant">
                <div class="variant-header">
                    <strong>Variant {i}</strong>
                    <span class="badge variant-{variant['status']}">{variant_status_badge}</span>
                </div>
                <div class="variant-content">{variant['content']}</div>
                <div class="variant-actions">
                    {f'<button onclick="approveVariant({post["id"]}, {variant["id"]})" class="btn btn-success btn-sm">✅ Approve</button>' if variant['status'] == 'pending' else ''}
                </div>
            </div>
            """
        
        posts_html += f"""
        <div class="post-card">
            <div class="post-header">
                <div class="post-meta">
                    <strong>{post['author_name']}</strong> (@{post['author_handle']})
                    <span class="post-date">{post['scraped_at']}</span>
                </div>
                <span class="badge status-{post['status'].replace('_', '-')}" style="background-color: {status_color}">
                    {post['status'].replace('_', ' ').title()}
                </span>
            </div>
            <div class="post-content">
                <div class="original-post">
                    <strong>Original Post:</strong>
                    <p>{post['original_content'][:500]}{'...' if len(post['original_content']) > 500 else ''}</p>
                </div>
                <details>
                    <summary>Show AI Variants ({len(post.get('variants', []))})</summary>
                    <div class="variants">
                        {variants_html}
                    </div>
                </details>
            </div>
            <div class="post-actions">
                <button onclick="regenerateVariants({post['id']})" class="btn btn-primary btn-sm">🔄 Regenerate AI</button>
                <button onclick="rejectPost({post['id']})" class="btn btn-danger btn-sm">❌ Reject All</button>
                <button onclick="deletePost({post['id']})" class="btn btn-danger btn-sm">🗑️ Delete</button>
            </div>
        </div>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>LinkedIn Reposter - Admin Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: #f5f5f5;
                color: #333;
                line-height: 1.6;
            }}
            
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
            }}
            
            header {{
                background: white;
                padding: 20px;
                margin-bottom: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            
            h1 {{
                margin-bottom: 10px;
                color: #0a66c2;
            }}
            
            .stats {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }}
            
            .stat-card {{
                background: white;
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                text-align: center;
            }}
            
            .stat-value {{
                font-size: 32px;
                font-weight: bold;
                color: #0a66c2;
            }}
            
            .stat-label {{
                font-size: 14px;
                color: #666;
                margin-top: 5px;
            }}
            
            .filters {{
                background: white;
                padding: 15px;
                margin-bottom: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
                align-items: center;
            }}
            
            select, input {{
                padding: 8px 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
            }}
            
            .post-card {{
                background: white;
                padding: 20px;
                margin-bottom: 15px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            
            .post-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
                padding-bottom: 15px;
                border-bottom: 1px solid #eee;
            }}
            
            .post-meta {{
                display: flex;
                flex-direction: column;
                gap: 5px;
            }}
            
            .post-date {{
                font-size: 14px;
                color: #666;
            }}
            
            .badge {{
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 600;
                color: white;
            }}
            
            .original-post {{
                margin-bottom: 15px;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 6px;
            }}
            
            .original-post p {{
                margin-top: 8px;
                white-space: pre-wrap;
            }}
            
            details {{
                margin-top: 15px;
            }}
            
            summary {{
                cursor: pointer;
                padding: 10px;
                background: #f8f9fa;
                border-radius: 4px;
                font-weight: 600;
                user-select: none;
            }}
            
            summary:hover {{
                background: #e9ecef;
            }}
            
            .variants {{
                margin-top: 15px;
                display: grid;
                gap: 15px;
            }}
            
            .variant {{
                padding: 15px;
                border: 1px solid #ddd;
                border-radius: 6px;
                background: #fafafa;
            }}
            
            .variant-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }}
            
            .variant-content {{
                margin: 10px 0;
                white-space: pre-wrap;
            }}
            
            .variant-actions {{
                margin-top: 10px;
            }}
            
            .variant-pending {{
                background: #fff3cd;
                color: #856404;
            }}
            
            .variant-approved {{
                background: #d4edda;
                color: #155724;
            }}
            
            .variant-rejected {{
                background: #f8d7da;
                color: #721c24;
            }}
            
            .variant-posted {{
                background: #d1ecf1;
                color: #0c5460;
            }}
            
            .post-actions {{
                margin-top: 15px;
                padding-top: 15px;
                border-top: 1px solid #eee;
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
            }}
            
            .btn {{
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                transition: all 0.2s;
            }}
            
            .btn:hover {{
                opacity: 0.9;
                transform: translateY(-1px);
            }}
            
            .btn-sm {{
                padding: 6px 12px;
                font-size: 13px;
            }}
            
            .btn-primary {{
                background: #0a66c2;
                color: white;
            }}
            
            .btn-success {{
                background: #28a745;
                color: white;
            }}
            
            .btn-danger {{
                background: #dc3545;
                color: white;
            }}
            
            .empty-state {{
                background: white;
                padding: 60px 20px;
                text-align: center;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            
            .empty-state-icon {{
                font-size: 64px;
                margin-bottom: 20px;
            }}
            
            .nav-links {{
                display: flex;
                gap: 15px;
                margin-top: 15px;
            }}
            
            .nav-links a {{
                color: #0a66c2;
                text-decoration: none;
                padding: 8px 16px;
                background: #e7f3ff;
                border-radius: 4px;
                font-size: 14px;
            }}
            
            .nav-links a:hover {{
                background: #cfe5ff;
            }}
            
            .loading {{
                text-align: center;
                padding: 20px;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>📊 LinkedIn Reposter - Admin Dashboard</h1>
                <div class="nav-links">
                    <a href="/admin/dashboard">🏠 Dashboard</a>
                    <a href="/admin/vnc">🖥️ VNC Viewer</a>
                    <a href="/stats">📈 Stats API</a>
                    <a href="/docs">📚 API Docs</a>
                </div>
            </header>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value">{stats.get('total_posts', 0)}</div>
                    <div class="stat-label">Total Posts</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get('awaiting_approval', 0)}</div>
                    <div class="stat-label">Awaiting Approval</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get('approved', 0)}</div>
                    <div class="stat-label">Approved</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get('posted', 0)}</div>
                    <div class="stat-label">Posted</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get('rejected', 0)}</div>
                    <div class="stat-label">Rejected</div>
                </div>
            </div>
            
            <div class="filters">
                <label>
                    Status:
                    <select id="statusFilter" onchange="filterPosts()">
                        <option value="">All</option>
                        <option value="awaiting_approval" selected>Awaiting Approval</option>
                        <option value="approved">Approved</option>
                        <option value="rejected">Rejected</option>
                        <option value="posted">Posted</option>
                        <option value="failed">Failed</option>
                    </select>
                </label>
                <label>
                    Author:
                    <select id="authorFilter" onchange="filterPosts()">
                        <option value="">All Authors</option>
                    </select>
                </label>
                <button onclick="window.location.reload()" class="btn btn-primary btn-sm">🔄 Refresh</button>
            </div>
            
            <div id="posts-container">
                {posts_html if posts_html else '<div class="empty-state"><div class="empty-state-icon">📭</div><h2>No posts found</h2><p>Try adjusting your filters or wait for the next scrape.</p></div>'}
            </div>
        </div>
        
        <script>
            async function approveVariant(postId, variantId) {{
                if (!confirm('Approve this variant for posting?')) return;
                
                try {{
                    const response = await fetch(`/admin/posts/${{postId}}/approve/${{variantId}}`, {{
                        method: 'POST'
                    }});
                    
                    if (response.ok) {{
                        alert('✅ Variant approved! Post will be queued for publishing.');
                        window.location.reload();
                    }} else {{
                        const error = await response.json();
                        alert('❌ Error: ' + (error.detail || 'Failed to approve'));
                    }}
                }} catch (err) {{
                    alert('❌ Network error: ' + err.message);
                }}
            }}
            
            async function regenerateVariants(postId) {{
                if (!confirm('Regenerate AI variants for this post? This will create 3 new variants.')) return;
                
                document.body.style.cursor = 'wait';
                
                try {{
                    const response = await fetch(`/admin/posts/${{postId}}/regenerate`, {{
                        method: 'POST'
                    }});
                    
                    if (response.ok) {{
                        alert('✅ Variants regenerated successfully!');
                        window.location.reload();
                    }} else {{
                        const error = await response.json();
                        alert('❌ Error: ' + (error.detail || 'Failed to regenerate'));
                    }}
                }} catch (err) {{
                    alert('❌ Network error: ' + err.message);
                }} finally {{
                    document.body.style.cursor = 'default';
                }}
            }}
            
            async function rejectPost(postId) {{
                if (!confirm('Reject all variants for this post?')) return;
                
                try {{
                    const response = await fetch(`/admin/posts/${{postId}}/reject`, {{
                        method: 'POST'
                    }});
                    
                    if (response.ok) {{
                        alert('✅ Post rejected');
                        window.location.reload();
                    }} else {{
                        const error = await response.json();
                        alert('❌ Error: ' + (error.detail || 'Failed to reject'));
                    }}
                }} catch (err) {{
                    alert('❌ Network error: ' + err.message);
                }}
            }}
            
            async function deletePost(postId) {{
                if (!confirm('⚠️ Permanently delete this post and all variants? This cannot be undone!')) return;
                
                try {{
                    const response = await fetch(`/admin/posts/${{postId}}`, {{
                        method: 'DELETE'
                    }});
                    
                    if (response.ok) {{
                        alert('✅ Post deleted');
                        window.location.reload();
                    }} else {{
                        const error = await response.json();
                        alert('❌ Error: ' + (error.detail || 'Failed to delete'));
                    }}
                }} catch (err) {{
                    alert('❌ Network error: ' + err.message);
                }}
            }}
            
            function filterPosts() {{
                const status = document.getElementById('statusFilter').value;
                const author = document.getElementById('authorFilter').value;
                const params = new URLSearchParams();
                if (status) params.set('status', status);
                if (author) params.set('author', author);
                window.location.href = '/admin/dashboard?' + params.toString();
            }}
        </script>
    </body>
    </html>
    """
    
    return html
