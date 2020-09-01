from dependency import *
from navigation import *

def init(board):
    # init board
    state['configuration'] = board.configuration
    state['me'] = board.current_player_id
    state['playerNum'] = len(board.players)
    state['memory'] = {}


def encode(board):
    global state
    
    # direct information
    state['currentHalite'] = board.current_player.halite
    state['next'] = np.zeros((board.configuration.size,board.configuration.size))
    state['board'] = board
    state['memory'][board.step] = {}
    state['memory'][board.step]['board'] = board
    state['cells'] = board.cells.values()
    state['ships'] = board.ships.values()
    state['myShips'] = board.current_player.ships
    state['shipyards'] = board.shipyards.values()
    state['myShipyards'] = board.current_player.shipyards
    N = state['configuration'].size

    # Halite 
    state['haliteMap'] = np.zeros((N, N))
    for cell in state['cells']:
        state['haliteMap'][cell.position.x][cell.position.y] = cell.halite
    # Halite Spread
    state['haliteSpread'] = np.copy(state['haliteMap'])
    for i in range(1,5):
        state['haliteSpread'] += np.roll(state['haliteMap'],i,axis=0) * 0.5**i
        state['haliteSpread'] += np.roll(state['haliteMap'],-i,axis=0) * 0.5**i
    temp = state['haliteSpread'].copy()
    for i in range(1,5):
        state['haliteSpread'] += np.roll(temp,i,axis=1) * 0.5**i
        state['haliteSpread'] += np.roll(temp,-i,axis=1) *  0.5**i
    # Ships
    state['shipMap'] = np.zeros((state['playerNum'], N, N))
    state['enemyShips'] = []
    for ship in state['ships']:
        state['shipMap'][ship.player_id][ship.position.x][ship.position.y] = 1
        if ship.player_id != state['me']:
            state['enemyShips'].append(ship)
    # Shipyards
    state['shipyardMap'] = np.zeros((state['playerNum'], N, N))
    state['enemyShipyards'] = []
    for shipyard in state['shipyards']:
        state['shipyardMap'][shipyard.player_id][shipyard.position.x][shipyard.position.y] = 1
        if shipyard.player_id != state['me']:
            state['enemyShipyards'].append(shipyard)
    # Total Halite
    state['haliteTotal'] = np.sum(state['haliteMap'])
    # Mean Halite 
    state['haliteMean'] = state['haliteTotal'] / (N**2)
    # Estimated "value" of a ship
    #totalShips = len(state['ships'])
    #state['shipValue'] = state['haliteTotal'] / state
    state['shipValue'] = ship_value()
    # Friendly units
    state['ally'] = state['shipMap'][state['me']]
    # Friendly shipyards
    state['allyShipyard'] = state['shipyardMap'][state['me']]
    # Enemy units
    state['enemy'] = np.sum(state['shipMap'], axis=0) - state['ally']
    # Enemy shipyards
    state['enemyShipyard'] = np.sum(state['shipyardMap'], axis=0) - state['allyShipyard']
    # Closest shipyard
    state['closestShipyard'] = closest_shipyard(state['myShipyards'])
    # Control map
    state['controlMap'] = control_map(state['ally']-state['enemy'],state['allyShipyard']-state['enemyShipyard'])
    state['negativeControlMap'] = control_map(-state['enemy'],-state['enemyShipyard'])
    state['positiveControlMap'] = control_map(state['ally'],state['allyShipyard'])
    #Enemy ship labeled by halite. If none, infinity
    state['enemyShipHalite'] = np.zeros((N, N))
    state['enemyShipHalite'] += np.Infinity
    for ship in state['ships']:
        if ship.player.id != state['me']:
            state['enemyShipHalite'][ship.position.x][ship.position.y] = ship.halite
    # Avoidance map (Places not to go for each ship)
    for ship in state['myShips']:
        state[ship] = {}
        state[ship]['blocked'] = get_avoidance(ship)
        state[ship]['danger'] = get_danger(ship.halite)
    # Who we should attack
    if len(state['board'].opponents) > 0:
        state['killTarget'] = get_target()
    
def get_avoidance(s):
    threshold = s.halite
    #Enemy units
    temp = np.where(state['enemyShipHalite'] < threshold, 1, 0)
    enemyBlock = np.copy(temp)
    enemyBlock = enemyBlock + np.roll(temp,1,axis=0)
    enemyBlock = enemyBlock + np.roll(temp,-1,axis=0)
    enemyBlock = enemyBlock + np.roll(temp,1,axis=1)
    enemyBlock = enemyBlock + np.roll(temp,-1,axis=1)

    enemyBlock = enemyBlock + state['enemyShipyard']

    blocked = enemyBlock
    blocked = np.where(blocked>0,1,0)
    return blocked

def get_danger(s):
    threshold = s
    dangerMap = np.where(state['enemyShipHalite'] < threshold, 1, 0)
    temp = dangerMap.copy()
    for i in range(1,4):
        dangerMap = np.add(dangerMap,np.roll(temp,i,axis=0) * 0.7**i,casting="unsafe")
        dangerMap += np.roll(temp,-i,axis=0) * 0.7**i
    temp = dangerMap.copy()
    for i in range(1,4):
        dangerMap += np.roll(temp,i,axis=1) * 0.7**i
        dangerMap += np.roll(temp,-i,axis=1) * 0.7**i
    return dangerMap
    

def closest_shipyard(shipyards):
    N = state['configuration'].size
    res = [[None for y in range(N)]for x in range(N)]
    for x in range(N):
        for y in range(N):
            minimum = math.inf
            for shipyard in shipyards:
                if dist(Point(x,y),shipyard.position) < minimum:
                    minimum = dist(Point(x,y),shipyard.position)
                    res[x][y] = shipyard.position
    return res
    
def control_map(ships,shipyards):
    ITERATIONS = 3

    res = np.copy(ships)
    for i in range(1,ITERATIONS+1):
        res += np.roll(ships,i,axis=0) * 0.5**i
        res += np.roll(ships,-i,axis=0) * 0.5**i
    temp = res.copy()
    for i in range(1,ITERATIONS+1):
        res += np.roll(temp,i,axis=1) * 0.5**i
        res += np.roll(temp,-i,axis=1) * 0.5**i
    
    return res + shipyards
        
def flood_fill(hmap, sources, threshold):
    # returns a boolean map indicating filled areas
    dirs = zip([0, 1, 0, -1], [1, 0, -1, 0])
    vis = np.zero_like(hmap, dtype=bool)
    def dfs(x, y):
        if vis[x, y]: return
        vis[x, y] = True
        for dx, dy in dirs:
            nx, ny = (x + dx) % N, (y + dy) % N
            if not vis[nx, ny] and hmap[nx, ny] <= threshold:
                dfs(nx, ny)
    for source in sources: dfs(source.x, source.y)
    return vis

def get_target():
    board = state['board']
    me = board.current_player
    idx,v = 0, -math.inf
    for i,opponent in enumerate(board.opponents):
        value = 0
        if opponent.halite-me.halite > 0:
            value = -(opponent.halite-me.halite)
        else:
            value = (opponent.halite-me.halite) * 5
        if value > v:
            v = value
            idx = i
    return board.opponents[idx]

def ship_value():
    # 普及一胎，控制二胎，消灭三胎
    if len(state['myShips']) >= 60:
        return 0
    res = state['haliteMean'] * 0.25 * (state['configuration']['episodeSteps']- 30 - state['board'].step) * weights[4][0]
    res += (len(state['ships']) - len(state['myShips'])) ** 1.5 * weights[4][1]
    res += len(state['myShips'])  ** 1.5 * weights[4][2]
    return res 