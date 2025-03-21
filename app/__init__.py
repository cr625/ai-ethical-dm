from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    from app.models.user import User
    return User.query.get(int(user_id))

def create_app(config_name='default'):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Load configuration
    from app.config import config
    app.config.from_object(config[config_name])
    
    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    
    # Register blueprints
    from app.routes.scenarios import scenarios_bp
    from app.routes.worlds import worlds_bp
    from app.routes.auth import auth_bp
    app.register_blueprint(scenarios_bp)
    app.register_blueprint(worlds_bp)
    app.register_blueprint(auth_bp)
    
    # Create routes
    @app.route('/')
    def index():
        return render_template('index.html')
    
    @app.route('/guidelines')
    def guidelines():
        from app.services import MCPClient
        client = MCPClient()
        try:
            guidelines_data = client.get_guidelines()
            return render_template('guidelines.html', guidelines=guidelines_data.get('guidelines', []))
        except Exception as e:
            return render_template('guidelines.html', guidelines=[], error=str(e))
    
    @app.route('/cases')
    def cases():
        from app.services import MCPClient
        client = MCPClient()
        try:
            cases_data = client.get_cases()
            return render_template('cases.html', cases=cases_data.get('cases', []))
        except Exception as e:
            return render_template('cases.html', cases=[], error=str(e))
    
    return app
