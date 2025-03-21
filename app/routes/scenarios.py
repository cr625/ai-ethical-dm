from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from app import db
from app.models.scenario import Scenario
from app.models.character import Character
from app.models.condition import Condition
from app.models.condition_type import ConditionType
from app.models.resource import Resource
from app.models.resource_type import ResourceType
from app.models.domain import Domain
from app.models.world import World
from app.models.role import Role
from app.services import EventEngine, DecisionEngine
from app.services.mcp_client import MCPClient

scenarios_bp = Blueprint('scenarios', __name__, url_prefix='/scenarios')

# API endpoints
@scenarios_bp.route('/api', methods=['GET'])
def api_get_scenarios():
    """API endpoint to get all scenarios."""
    scenarios = Scenario.query.all()
    return jsonify({
        'success': True,
        'data': [scenario.to_dict() for scenario in scenarios]
    })

@scenarios_bp.route('/api/<int:id>', methods=['GET'])
def api_get_scenario(id):
    """API endpoint to get a specific scenario by ID."""
    scenario = Scenario.query.get_or_404(id)
    return jsonify({
        'success': True,
        'data': scenario.to_dict()
    })

# Web routes
@scenarios_bp.route('/', methods=['GET'])
def list_scenarios():
    """Display all scenarios."""
    # Get world filter from query parameters
    world_id = request.args.get('world_id', type=int)
    
    # Filter scenarios by world if specified
    if world_id:
        scenarios = Scenario.query.filter_by(world_id=world_id).all()
    else:
        scenarios = Scenario.query.all()
    
    worlds = World.query.all()
    return render_template('scenarios.html', scenarios=scenarios, worlds=worlds, selected_world_id=world_id)

@scenarios_bp.route('/new', methods=['GET'])
def new_scenario():
    """Display form to create a new scenario."""
    worlds = World.query.all()
    world_id = request.args.get('world_id', type=int)
    world = None
    if world_id:
        world = World.query.get(world_id)
    return render_template('create_scenario.html', worlds=worlds, world=world)

@scenarios_bp.route('/<int:id>', methods=['GET'])
def view_scenario(id):
    """Display a specific scenario."""
    scenario = Scenario.query.get_or_404(id)
    return render_template('scenario_detail.html', scenario=scenario)

@scenarios_bp.route('/<int:id>/edit', methods=['GET'])
def edit_scenario(id):
    """Display form to edit an existing scenario."""
    scenario = Scenario.query.get_or_404(id)
    worlds = World.query.all()
    return render_template('edit_scenario.html', scenario=scenario, worlds=worlds)

@scenarios_bp.route('/<int:id>/edit', methods=['POST'])
def update_scenario_form(id):
    """Update an existing scenario from form data."""
    scenario = Scenario.query.get_or_404(id)
    
    # Get world (required)
    world_id = request.form.get('world_id')
    if not world_id:
        flash('World ID is required', 'danger')
        return redirect(url_for('scenarios.edit_scenario', id=scenario.id))
    
    try:
        world_id = int(world_id)
        world = World.query.get(world_id)
        if not world:
            flash(f'World with ID {world_id} not found', 'danger')
            return redirect(url_for('scenarios.edit_scenario', id=scenario.id))
    except ValueError:
        flash('Invalid world ID', 'danger')
        return redirect(url_for('scenarios.edit_scenario', id=scenario.id))
    
    # Update scenario fields
    scenario.name = request.form.get('name', '')
    scenario.description = request.form.get('description', '')
    scenario.world_id = world_id
    
    db.session.commit()
    
    flash('Scenario updated successfully', 'success')
    return redirect(url_for('scenarios.view_scenario', id=scenario.id))

# Character routes
@scenarios_bp.route('/<int:id>/characters/new', methods=['GET'])
def new_character(id):
    """Display form to add a character to a scenario."""
    scenario = Scenario.query.get_or_404(id)
    world = World.query.get(scenario.world_id)
    
    # Get roles for the scenario's world from the database
    db_roles = Role.query.filter_by(world_id=scenario.world_id).all()
    
    # Get condition types for the scenario's world
    condition_types = ConditionType.query.filter_by(world_id=scenario.world_id).all()
    
    # Get roles from the ontology if the world has an ontology source
    ontology_roles = []
    if world and world.ontology_source:
        try:
            mcp_client = MCPClient()
            entities = mcp_client.get_world_entities(world.ontology_source, entity_type="roles")
            if entities and 'entities' in entities and 'roles' in entities['entities']:
                ontology_roles = entities['entities']['roles']
        except Exception as e:
            print(f"Error retrieving roles from ontology: {str(e)}")
    
    # Debug information
    print(f"Found {len(db_roles)} database roles for world_id {scenario.world_id}")
    print(f"Found {len(ontology_roles)} ontology roles for world_id {scenario.world_id}")
    
    print(f"Found {len(condition_types)} condition types for world_id {scenario.world_id}")
    
    return render_template(
        'create_character.html', 
        scenario=scenario, 
        roles=db_roles, 
        ontology_roles=ontology_roles,
        condition_types=condition_types
    )

@scenarios_bp.route('/<int:id>/characters', methods=['POST'])
def add_character(id):
    """Add a character to a scenario."""
    scenario = Scenario.query.get_or_404(id)
    data = request.json
    
    # Check if the role_id is an ontology URI (starts with http)
    role_id = data.get('role_id')
    role_name = None
    role_description = None
    
    if role_id and isinstance(role_id, str) and role_id.startswith('http'):
        # This is an ontology role
        # Get the role name and description from the ontology
        world = World.query.get(scenario.world_id)
        if world and world.ontology_source:
            try:
                mcp_client = MCPClient()
                entities = mcp_client.get_world_entities(world.ontology_source, entity_type="roles")
                if entities and 'entities' in entities and 'roles' in entities['entities']:
                    for role in entities['entities']['roles']:
                        if role['id'] == role_id:
                            role_name = role['label']
                            role_description = role['description']
                            break
            except Exception as e:
                print(f"Error retrieving role from ontology: {str(e)}")
        
        # Create or find a role in the database to associate with this character
        db_role = Role.query.filter_by(ontology_uri=role_id, world_id=scenario.world_id).first()
        if not db_role and role_name:
            # Create a new role in the database
            db_role = Role(
                name=role_name,
                description=role_description,
                world_id=scenario.world_id,
                ontology_uri=role_id
            )
            db.session.add(db_role)
            db.session.flush()  # Get the ID without committing
        
        # Use the database role ID if available
        if db_role:
            role_id = db_role.id
    
    # Create character
    character = Character(
        scenario=scenario,
        name=data['name'],
        role_id=role_id,
        attributes=data.get('attributes', {})
    )
    
    # Set the role name for backward compatibility
    if character.role_id:
        if role_name:  # We already have the name from the ontology
            character.role = role_name
        else:
            # Get the role name from the database
            role = Role.query.get(character.role_id)
            if role:
                character.role = role.name
    
    db.session.add(character)
    
    # Add conditions if provided
    for cond_data in data.get('conditions', []):
        condition = Condition(
            character=character,
            name=cond_data['name'],
            description=cond_data.get('description', ''),
            severity=cond_data.get('severity', 1),
            condition_type_id=cond_data.get('condition_type_id')
        )
        db.session.add(condition)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Character added successfully',
        'data': {
            'id': character.id,
            'name': character.name,
            'role': character.role
        }
    })

# Resource routes
@scenarios_bp.route('/<int:id>/resources/new', methods=['GET'])
def new_resource(id):
    """Display form to add a resource to a scenario."""
    scenario = Scenario.query.get_or_404(id)
    # Get resource types for the scenario's world
    resource_types = ResourceType.query.filter_by(world_id=scenario.world_id).all()
    
    # Debug information
    print(f"Found {len(resource_types)} resource types for world_id {scenario.world_id}:")
    for rt in resource_types:
        print(f"ID: {rt.id}, Name: {rt.name}, Category: {rt.category}")
        print(f"Description: {rt.description}")
        print(f"Ontology URI: {rt.ontology_uri}")
        print("-" * 50)
    
    return render_template('create_resource.html', scenario=scenario, resource_types=resource_types)

@scenarios_bp.route('/<int:id>/resources', methods=['POST'])
def add_resource(id):
    """Add a resource to a scenario."""
    scenario = Scenario.query.get_or_404(id)
    data = request.json
    
    # Create resource
    resource = Resource(
        scenario=scenario,
        name=data['name'],
        resource_type_id=data.get('resource_type_id'),
        quantity=data.get('quantity', 1),
        description=data.get('description', '')
    )
    
    # If resource_type_id is provided, get the type for backward compatibility
    if resource.resource_type_id:
        resource_type = ResourceType.query.get(resource.resource_type_id)
        if resource_type:
            resource.type = resource_type.name
    else:
        # Use the type field if provided
        resource.type = data.get('type', '')
    
    db.session.add(resource)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Resource added successfully',
        'data': {
            'id': resource.id,
            'name': resource.name,
            'type': resource.type,
            'quantity': resource.quantity
        }
    })

# Event routes
@scenarios_bp.route('/<int:id>/events/new', methods=['GET'])
def new_event(id):
    """Display form to add an event to a scenario."""
    scenario = Scenario.query.get_or_404(id)
    return render_template('create_event.html', scenario=scenario)

@scenarios_bp.route('/<int:id>/events', methods=['POST'])
def add_event(id):
    """Add an event to a scenario."""
    from app.models.event import Event
    
    scenario = Scenario.query.get_or_404(id)
    data = request.json
    
    # Get character if provided
    character_id = data.get('character_id')
    character = None
    if character_id:
        character = Character.query.get(character_id)
    
    # Create event
    event = Event(
        scenario=scenario,
        event_time=data['event_time'],
        description=data['description'],
        character=character,
        action_type=data.get('action_type'),
        metadata=data.get('metadata', {})
    )
    db.session.add(event)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Event added successfully',
        'data': {
            'id': event.id,
            'event_time': event.event_time.isoformat(),
            'description': event.description
        }
    })

# Decision routes
@scenarios_bp.route('/<int:id>/decisions/new', methods=['GET'])
def new_decision(id):
    """Display form to add a decision to a scenario."""
    scenario = Scenario.query.get_or_404(id)
    return render_template('create_decision.html', scenario=scenario)

@scenarios_bp.route('/<int:id>/decisions', methods=['POST'])
def add_decision(id):
    """Add a decision to a scenario."""
    from app.models.decision import Decision
    
    scenario = Scenario.query.get_or_404(id)
    data = request.json
    
    # Get character if provided
    character_id = data.get('character_id')
    character = None
    if character_id:
        character = Character.query.get(character_id)
    
    # Create decision
    decision = Decision(
        scenario=scenario,
        decision_time=data['decision_time'],
        description=data['description'],
        options=data['options'],
        character=character,
        context=data.get('context', '')
    )
    db.session.add(decision)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Decision added successfully',
        'data': {
            'id': decision.id,
            'decision_time': decision.decision_time.isoformat(),
            'description': decision.description,
            'options': decision.options
        }
    })

@scenarios_bp.route('/', methods=['POST'])
def create_scenario():
    """Create a new scenario."""
    # Check if the request is JSON or form data
    if request.is_json:
        data = request.json
    else:
        data = request.form
    
    # Get world (required)
    world_id = data.get('world_id')
    if not world_id:
        if request.is_json:
            return jsonify({
                'success': False,
                'message': 'World ID is required'
            }), 400
        else:
            flash('World ID is required', 'danger')
            return redirect(url_for('scenarios.new_scenario'))
    
    try:
        world_id = int(world_id)
        world = World.query.get(world_id)
        if not world:
            if request.is_json:
                return jsonify({
                    'success': False,
                    'message': f'World with ID {world_id} not found'
                }), 404
            else:
                flash(f'World with ID {world_id} not found', 'danger')
                return redirect(url_for('scenarios.new_scenario'))
    except ValueError:
        if request.is_json:
            return jsonify({
                'success': False,
                'message': 'Invalid world ID'
            }), 400
        else:
            flash('Invalid world ID', 'danger')
            return redirect(url_for('scenarios.new_scenario'))
    
    # Create scenario
    scenario = Scenario(
        name=data.get('name', ''),
        description=data.get('description', ''),
        metadata={},
        world_id=world_id
    )
    db.session.add(scenario)
    
    # Add characters if provided (JSON only)
    if request.is_json:
        for char_data in data.get('characters', []):
            character = Character(
                scenario=scenario,
                name=char_data['name'],
                role=char_data.get('role', ''),
                attributes=char_data.get('attributes', {})
            )
            db.session.add(character)
            
            # Add conditions if provided
            for cond_data in char_data.get('conditions', []):
                condition = Condition(
                    character=character,
                    name=cond_data['name'],
                    description=cond_data.get('description', ''),
                    severity=cond_data.get('severity', 1)
                )
                db.session.add(condition)
        
        # Add resources if provided
        for res_data in data.get('resources', []):
            resource = Resource(
                scenario=scenario,
                name=res_data['name'],
                type=res_data.get('type', ''),
                quantity=res_data.get('quantity', 1),
                description=res_data.get('description', '')
            )
            db.session.add(resource)
    
    db.session.commit()
    
    if request.is_json:
        return jsonify({
            'success': True,
            'message': 'Scenario created successfully',
            'data': scenario.to_dict()
        }), 201
    else:
        flash('Scenario created successfully', 'success')
        return redirect(url_for('scenarios.view_scenario', id=scenario.id))

@scenarios_bp.route('/<int:id>', methods=['PUT'])
def update_scenario(id):
    """Update an existing scenario."""
    scenario = Scenario.query.get_or_404(id)
    data = request.json
    
    # Update scenario fields
    if 'name' in data:
        scenario.name = data['name']
    if 'description' in data:
        scenario.description = data['description']
    if 'metadata' in data:
        scenario.metadata = data['metadata']
    
    # Update world if provided
    if 'world_id' in data:
        world = World.query.get(data['world_id'])
        if not world:
            return jsonify({
                'success': False,
                'message': f'World with ID {data["world_id"]} not found'
            }), 404
        scenario.world_id = world.id
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Scenario updated successfully',
        'data': scenario.to_dict()
    })

@scenarios_bp.route('/<int:id>', methods=['DELETE'])
def delete_scenario(id):
    """Delete a scenario via API."""
    scenario = Scenario.query.get_or_404(id)
    db.session.delete(scenario)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Scenario deleted successfully'
    })

@scenarios_bp.route('/<int:id>/delete', methods=['POST'])
def delete_scenario_form(id):
    """Delete a scenario from web form."""
    scenario = Scenario.query.get_or_404(id)
    db.session.delete(scenario)
    db.session.commit()
    
    flash('Scenario deleted successfully', 'success')
    return redirect(url_for('scenarios.list_scenarios'))

# References routes
@scenarios_bp.route('/<int:id>/references', methods=['GET'])
def scenario_references(id):
    """Display references for a scenario."""
    scenario = Scenario.query.get_or_404(id)
    
    # Get search query from request parameters
    query = request.args.get('query', '')
    
    # Initialize MCP client
    mcp_client = MCPClient()
    
    # Get references
    if query:
        # Search with the provided query
        references = mcp_client.search_zotero_items(query, limit=10)
    else:
        # Get references based on scenario content
        references = mcp_client.get_references_for_scenario(scenario)
    
    return render_template('scenario_references.html', scenario=scenario, references=references, query=query)

@scenarios_bp.route('/<int:id>/references/<item_key>/citation', methods=['GET'])
def get_reference_citation(id, item_key):
    """Get citation for a reference."""
    scenario = Scenario.query.get_or_404(id)
    style = request.args.get('style', 'apa')
    
    # Initialize MCP client
    mcp_client = MCPClient()
    
    # Get citation
    try:
        citation = mcp_client.get_zotero_citation(item_key, style)
        return jsonify({
            'success': True,
            'citation': citation
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scenarios_bp.route('/<int:id>/references/add', methods=['POST'])
def add_reference(id):
    """Add a reference to the Zotero library."""
    scenario = Scenario.query.get_or_404(id)
    data = request.json
    
    # Initialize MCP client
    mcp_client = MCPClient()
    
    # Add reference
    try:
        result = mcp_client.add_zotero_item(
            item_type=data.get('item_type', 'journalArticle'),
            title=data.get('title', ''),
            creators=data.get('creators', []),
            additional_fields=data.get('additional_fields', {})
        )
        
        return jsonify({
            'success': True,
            'message': 'Reference added successfully',
            'data': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
