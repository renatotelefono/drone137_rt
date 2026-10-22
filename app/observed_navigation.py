"""Bounded exploration of unknown space from timestamped range packets only."""
import heapq
import math


class ObservedNavigation:
    CELL=.05
    def __init__(self,width,depth,home,radius,margin,braking_acceleration=.8):
        self.width,self.depth,self.home=width,depth,home;self.radius=radius;self.margin=margin
        if not math.isfinite(braking_acceleration) or braking_acceleration<=0:raise ValueError('Positive braking acceleration required')
        self.braking_acceleration=braking_acceleration
        self.nx,self.ny=math.ceil(width/self.CELL),math.ceil(depth/self.CELL)
        self.grid=[0]*(self.nx*self.ny);self.evidence=[0]*len(self.grid);self.last=-math.inf;self.scans=0;self.ranges=[]
        self.safe=set();self.preferred=set();self.visited=set();self.events=[]
        extent=math.ceil((radius+margin)/self.CELL)
        self.offsets=[(dx,dy) for dx in range(-extent,extent+1) for dy in range(-extent,extent+1)
                      if math.hypot(max(0,abs(dx)*self.CELL-self.CELL/2),max(0,abs(dy)*self.CELL-self.CELL/2))<radius+margin]

    def cell(self,p):
        if not (0<=p[0]<self.width and 0<=p[1]<self.depth):raise ValueError('Position outside operating boundary')
        return int(p[1]/self.CELL)*self.nx+int(p[0]/self.CELL)

    def center(self,i):return [(i%self.nx+.5)*self.CELL,(i//self.nx+.5)*self.CELL]

    def integrate(self,pose,ranges,now):
        if not ranges or not any(r['valid'] and 0<=now-r['time']<=.35 for r in ranges):return
        x,y,yaw=pose;free=set();occupied=set();accepted=[]
        for r in ranges:
            if not r['valid'] or not 0<=now-r['time']<=.35 or not math.isfinite(r['distance']) or not 0<r['distance']<=r['max_range']:continue
            angle=yaw+r['angle_body'];distance=r['distance'];dx,dy=math.cos(angle),math.sin(angle)
            accepted.append({**r,'angle':angle})
            for i in range(1,math.ceil(distance/(self.CELL/2))+1):
                along=min(i*self.CELL/2,distance);p=[x+dx*along,y+dy*along]
                if not (0<=p[0]<self.width and 0<=p[1]<self.depth):break
                cell=self.cell(p)
                if r['hit'] and along>=distance-.04:occupied.add(cell)
                else:free.add(cell)
        if not accepted:return
        for i in free-occupied:self.evidence[i]=max(-6,self.evidence[i]-2)
        for i in occupied:self.evidence[i]=min(6,self.evidence[i]+4)
        self.grid=[2 if e>=2 else 1 if e<=-2 else 0 for e in self.evidence]
        # A sensor origin is observed, not a preloaded room or free-space disc.
        self.grid[self.cell([x,y])]=1
        # Vectorized binary erosion retains a 5 cm map without a Python loop
        # over every cell/rotor offset. Unknown cells remain impassable.
        import numpy as np
        free_grid=np.asarray(self.grid,dtype=np.uint8).reshape(self.ny,self.nx)==1
        safe=free_grid.copy()
        for dx,dy in self.offsets:
            x0,x1=max(0,-dx),min(self.nx,self.nx-dx);y0,y1=max(0,-dy),min(self.ny,self.ny-dy)
            shifted=np.zeros_like(safe);shifted[y0:y1,x0:x1]=free_grid[y0+dy:y1+dy,x0+dx:x1+dx];safe &= shifted
        self.safe=set(np.flatnonzero(safe).tolist())
        # Prefer an additional 10 cm from uncertain edges when space permits.
        # Hard clearance is unchanged; narrow, genuinely observed routes remain
        # available. This reduces edge-hugging caused by shortest-path tie breaks.
        preferred=safe.copy()
        for dx,dy in ((-2,0),(2,0),(0,-2),(0,2),(-1,-1),(-1,1),(1,-1),(1,1)):
            x0,x1=max(0,-dx),min(self.nx,self.nx-dx);y0,y1=max(0,-dy),min(self.ny,self.ny-dy)
            shifted=np.zeros_like(safe);shifted[y0:y1,x0:x1]=safe[y0+dy:y1+dy,x0+dx:x1+dx];preferred &= shifted
        self.preferred=set(np.flatnonzero(preferred).tolist())
        self.last=now;self.scans+=1;self.ranges=accepted;self.visited.add(self.cell([x,y]))

    def segment(self,start,end,preferred=False):
        n=max(1,math.ceil(math.dist(start[:2],end[:2])/(self.CELL/3)))
        cells=self.preferred if preferred else self.safe
        try:return all(self.cell([start[0]+(end[0]-start[0])*i/n,start[1]+(end[1]-start[1])*i/n]) in cells for i in range(n+1))
        except ValueError:return False

    def next_step(self,position,goal):
        start=self.cell(position);target=self.cell(goal)
        if start not in self.safe:raise RuntimeError('Insufficient observed clearance around aircraft')
        queue=[(0,start)];parent={start:None};costs={start:0}
        while queue:
            cost,cur=heapq.heappop(queue)
            if cost!=costs[cur]:continue
            if cur==target:break
            x,y=cur%self.nx,cur//self.nx
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                nxt=(y+dy)*self.nx+x+dx
                if 0<=x+dx<self.nx and 0<=y+dy<self.ny and nxt in self.safe:
                    value=cost+(1 if nxt in self.preferred else 4)
                    if value<costs.get(nxt,math.inf):
                        costs[nxt]=value;parent[nxt]=cur;heapq.heappush(queue,(value,nxt))
        if target not in parent:
            # Nearest reachable observed frontier. No target truth or world boxes.
            candidates=[i for i in parent if i!=start]
            if not candidates:raise RuntimeError('No reachable observed frontier')
            target=min(candidates,key=lambda i:(math.dist(self.center(i),goal[:2]),i in self.visited,i))
            if math.dist(self.center(target),goal[:2])>=math.dist(position[:2],goal[:2])-.05:
                raise RuntimeError('Goal is not reachable through observed space')
        path=[];cur=target
        while cur!=start:path.append(cur);cur=parent[cur]
        path.reverse()
        destination=goal[:2] if target==self.cell(goal) and self.segment(position,goal) else self.center(target)
        if start in self.preferred and not self.segment(position,destination,preferred=True):
            preferred=[self.center(i) for i in path if math.dist(position[:2],self.center(i))<=.8 and self.segment(position,self.center(i),preferred=True)]
            if preferred:return preferred[-1]
        if self.segment(position,destination):
            length=math.dist(position[:2],destination)
            return [position[i]+(destination[i]-position[i])*min(1,.7/max(length,1e-9)) for i in (0,1)]
        candidates=[self.center(i) for i in path if math.dist(position[:2],self.center(i))<=.8 and self.segment(position,self.center(i))]
        if not candidates:raise RuntimeError('No observed clearance for next motion')
        return candidates[-1]

    def motion_clear(self,position,goal,speed,now):
        if now-self.last>.35:return False
        angle=math.atan2(goal[1]-position[1],goal[0]-position[0]);needed=self.radius+self.margin+speed*(.25+max(0,now-self.last))+speed*speed/(2*self.braking_acceleration)
        rays=[r for r in self.ranges if abs(math.atan2(math.sin(r['angle']-angle),math.cos(r['angle']-angle)))<.35]
        return bool(rays) and min(r['distance'] for r in rays)>needed

    def report(self):
        return {'source':'Timestamped simulated column ranges + PX4 estimated pose; no obstacle manifest in planner',
                'scans':self.scans,'observed_fraction':sum(v!=0 for v in self.grid)/len(self.grid),
                'free_cells':self.grid.count(1),'occupied_cells':self.grid.count(2),'unknown_cells':self.grid.count(0),
                'visited_cells':len(self.visited),'grid':self.grid,'cell_m':self.CELL,'width_cells':self.nx,'events':self.events,
                'coverage_interpretation':'Range-map coverage, not camera/object visibility coverage'}
