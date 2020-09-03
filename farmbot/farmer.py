from encode import *
from agent import *
from dependency import *

# XXX
SCHEMA = [
    [0,0,3,3,0,0,0],
    [0,2,1,1,2,2,0],
    [0,2,1,1,1,1,3],
    [3,1,1,1,1,1,3],
    [3,1,1,1,1,2,0],
    [0,2,2,1,1,2,0],
    [0,0,0,3,3,0,0]
]
SCHEMA_SIZE = [7,7]

def wall_schema(): 
    # design wall structure according to shipyard pos

    if len(state['myShipyards']) == 0:
        return

    # find best shipyard
    best = None
    for shipyard in state['myShipyards']:  
        if best == None or state['farmMap'][shipyard.position.x][shipyard.position.y] > state['farmMap'][best.position.x][best.position.y]:
            best = shipyard

    # submit schema into farmMap
    farmMap = np.zeros((state['N'],state['N']))
    sPos = best.position
    for x in range(SCHEMA_SIZE[0]):
        for y in range(SCHEMA_SIZE[1]):
            xx = ((sPos.x - SCHEMA_SIZE[0]//2) + x + 21) % 21
            yy = ((sPos.y - SCHEMA_SIZE[0]//2) + y + 21) % 21
            farmMap[xx][yy] = SCHEMA[x][y]
    return farmMap

def farm(ships):
    global action
    cfg = state['configuration']
    board = state['board']
    me = board.current_player

    # Run when under attack
    shipsToAssign = []
    for ship in ships:
        if ship in action:
            continue 
        for target in get_adjacent(ship.position):
            if board.cells[target].ship != None:
                targetShip = board.cells[target].ship
                if targetShip.player.id != state['me'] and targetShip.halite < ship.halite:
                    action[ship] = (INF*2+state[ship]['danger'][ship.position.x][ship.position.y], ship, state['closestShipyard'][ship.position.x][ship.position.y])
        if ship in action:
            continue # continue its current action
        shipsToAssign.append(ship)
    

    # Get Targets
    targets = [] # (cell, type)
    farmMap = wall_schema()
    for i in board.cells.values():  # Filter targets
        pos = i.position
        # Wall
        if farmMap[pos.x][pos.y] >= 2:
            targets.append((i,'wall'))
        if farmMap[pos.x][pos.y] == 1:
            targets.append((i,'cell'))
    for i in range(len(shipsToAssign)):
        targets.append(None,'none')

    # Calculate rewards
    rewards = np.zeros((len(shipsToAssign), len(targets)))
    for i, ship in enumerate(shipsToAssign):
        for j, target in enumerate(targets):
            rewards[i, j] = get_farm_reward(ship, target)          

    # Assign rewards
    rows, cols = scipy.optimize.linear_sum_assignment(rewards, maximize=True)  # rows[i] -> cols[i]
    for r, c in zip(rows, cols):
        task = targets[c]
        if task[1] == 'cell':
            cell = cell = targets[c][0]
            if cell.halite == 0 and cell.shipyard == None and (cell.ship == None or cell.ship.player_id == state['me']):
                action[shipsToAssign[r]] = (0, shipsToAssign[r], targets[c][0].position)
            else:
                action[shipsToAssign[r]] = (rewards[r][c], shipsToAssign[r], targets[c][0].position)
        elif task[1] == 'guard':
            action[shipsToAssign[r]] = (0, shipsToAssign[r], targets[c][0].position)

def get_farm_reward(ship,target):
    
    cell = target[0]
    res = 0
    # Don't be stupid
    if state[ship]['blocked'][cell.position.x][cell.position.y] and cell.shipyard == None:
        res = 0
    if target[1] == 'wall':
        return wall_reward(ship,target)
    elif target[1] == 'none':
        return none_reward(ship,target)
    elif target[1] == 'cell':
        if (cell.ship is None or cell.ship.player_id == state['me']) and cell.halite > 0:
            res = farm_reward(ship,cell)
        elif cell.shipyard is None and cell.halite == 0 and (cell.ship is None or cell.ship.player_id == state['me']):
            res = farm_control_reward(ship,cell)
        elif cell.shipyard is not None and cell.shipyard.player_id == state['me']:
            res = farm_return_reward(ship,cell)
        elif cell.ship is not None and cell.ship.player_id != state['me']:
            res = farm_attack_reward(ship,cell)
        else:
            print("Shouldn't happen")
    
    return res

def wall_reward(ship,target):
    pass

def farm_control_reward(ship,target):
    pass

def none_reward(ship,target):
    return 1

def farm_reward(ship,target):
    pass

def farm_attack_reward(ship,target):
    pass

def farm_return_reward(ship,target):
    pass