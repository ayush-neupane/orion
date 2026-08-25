/**
 * Interactive 3D globe (react-three-fiber).
 * - Stylized continent outlines rendered as glowing line loops on the sphere.
 * - Fresnel atmosphere halo, exchange markers with pulse rings and
 *   great-circle connection arcs.
 * Clicking an exchange marker filters the dashboard to that region;
 * "GLOBAL" is available via the region pills in the header.
 */
import { useMemo, useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Html, Line, OrbitControls, Stars } from '@react-three/drei';
import * as THREE from 'three';
import { useMarketStore, type Region } from '../store/marketStore';

interface ExchangeMarker {
  region: Exclude<Region, 'GLOBAL'>;
  city: string;
  flag: string;
  lat: number;
  lon: number;
}

const EXCHANGES: ExchangeMarker[] = [
  { region: 'US', city: 'New York', flag: '🇺🇸', lat: 40.71, lon: -74.01 },
  { region: 'UK', city: 'London', flag: '🇬🇧', lat: 51.51, lon: -0.13 },
  { region: 'EU', city: 'Frankfurt', flag: '🇪🇺', lat: 50.11, lon: 8.68 },
  { region: 'JP', city: 'Tokyo', flag: '🇯🇵', lat: 35.68, lon: 139.69 },
  { region: 'IN', city: 'Mumbai', flag: '🇮🇳', lat: 19.08, lon: 72.88 },
];

function latLonToVector3(lat: number, lon: number,
  radius: number): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

/** Simplified continent outlines ([lon, lat] pairs) — stylized, low-poly. */
type Ring = Array<[number, number]>;

const NORTH_AMERICA: Ring = [
  [-168, 65], [-160, 70], [-150, 71], [-140, 69], [-130, 69], [-120, 69],
  [-110, 68], [-100, 68], [-90, 68], [-82, 66], [-75, 62], [-70, 60],
  [-65, 60], [-60, 56], [-55, 52], [-66, 44], [-70, 42], [-74, 40],
  [-76, 35], [-80, 32], [-81, 25], [-83, 29], [-89, 29], [-94, 29],
  [-97, 26], [-97, 21], [-94, 18], [-87, 21], [-88, 15], [-83, 9],
  [-80, 8], [-85, 11], [-92, 15], [-97, 16], [-105, 20], [-110, 23],
  [-114, 28], [-117, 33], [-122, 37], [-124, 41], [-124, 47], [-128, 51],
  [-132, 55], [-136, 58], [-146, 60], [-152, 58], [-158, 56], [-165, 60],
];

const SOUTH_AMERICA: Ring = [
  [-77, 7], [-72, 11], [-64, 10], [-60, 8], [-52, 5], [-50, 0], [-44, -2],
  [-38, -5], [-35, -8], [-39, -14], [-41, -22], [-48, -26], [-53, -34],
  [-58, -39], [-62, -41], [-65, -45], [-68, -50], [-69, -53], [-74, -50],
  [-73, -45], [-73, -37], [-71, -30], [-70, -18], [-76, -14], [-81, -6],
  [-80, 0], [-78, 4],
];

const AFRICA: Ring = [
  [-6, 35], [10, 37], [20, 32], [30, 31], [33, 28], [36, 22], [38, 18],
  [43, 11], [51, 11], [46, 2], [41, -2], [39, -7], [40, -15], [35, -20],
  [33, -26], [27, -34], [18, -34], [14, -26], [12, -18], [13, -10],
  [9, -1], [8, 4], [4, 6], [-4, 5], [-8, 4], [-13, 9], [-17, 14],
  [-16, 20], [-13, 26], [-9, 31],
];

const EURASIA: Ring = [
  [-9, 43], [-9, 37], [-6, 36], [0, 38], [5, 41], [10, 43], [14, 45],
  [19, 42], [21, 40], [24, 38], [27, 37], [30, 36], [36, 36], [34, 33],
  [34, 28], [39, 21], [43, 12], [50, 13], [55, 17], [59, 22], [57, 25],
  [51, 28], [48, 30], [52, 27], [58, 25], [62, 25], [67, 24], [70, 21],
  [73, 16], [76, 9], [80, 13], [84, 18], [88, 22], [91, 22], [92, 17],
  [94, 14], [98, 8], [103, 1], [102, 6], [100, 13], [105, 10], [109, 13],
  [106, 20], [108, 21], [113, 22], [117, 24], [121, 28], [122, 31],
  [119, 35], [121, 37], [125, 39], [126, 35], [129, 36], [129, 42],
  [132, 43], [135, 44], [138, 47], [142, 50], [147, 54], [155, 51],
  [162, 56], [163, 60], [170, 64], [178, 65], [175, 68], [160, 70],
  [150, 72], [140, 72], [130, 72], [120, 73], [110, 74], [100, 76],
  [90, 75], [80, 73], [72, 68], [60, 69], [50, 68], [40, 66], [37, 64],
  [30, 70], [25, 71], [18, 69], [12, 65], [5, 62], [5, 58], [8, 55],
  [5, 53], [0, 49], [-4, 48], [-1, 46], [-2, 43],
];

const AUSTRALIA: Ring = [
  [113, -22], [114, -26], [115, -33], [118, -35], [124, -33], [132, -32],
  [137, -35], [140, -38], [145, -38], [150, -37], [153, -32], [153, -27],
  [151, -24], [146, -19], [143, -14], [141, -13], [139, -17], [136, -15],
  [135, -12], [131, -12], [129, -15], [126, -14], [122, -17], [118, -20],
];

const GREENLAND: Ring = [
  [-45, 60], [-42, 62], [-40, 65], [-33, 68], [-25, 70], [-22, 72],
  [-25, 75], [-33, 78], [-45, 80], [-58, 76], [-62, 72], [-55, 68],
  [-52, 64], [-48, 61],
];

const UK_ISLES: Ring = [
  [-5, 50], [1, 51], [0, 53], [-2, 56], [-4, 58], [-6, 55], [-5, 52],
];

const JAPAN: Ring = [
  [130, 31], [132, 34], [137, 34], [140, 36], [141, 39], [141, 42],
  [143, 44], [145, 44], [142, 41], [140, 37], [137, 35], [133, 33],
];

const MADAGASCAR: Ring = [
  [44, -16], [47, -15], [50, -16], [49, -20], [47, -25], [44, -25],
  [43, -21],
];

const BORNEO: Ring = [
  [109, 1], [113, 3], [117, 4], [119, 1], [116, -3], [112, -3],
];

const SUMATRA: Ring = [
  [95, 5], [99, 2], [103, -2], [106, -6], [102, -5], [98, 0],
];

const NEW_GUINEA: Ring = [
  [131, -1], [136, -2], [141, -3], [146, -6], [148, -9], [143, -8],
  [138, -7], [134, -4],
];

const NEW_ZEALAND: Ring = [
  [173, -35], [176, -38], [174, -41], [171, -43], [167, -46], [170, -44],
  [172, -40],
];

/** Antarctic circle ring — closes the southern polar cap. */
const ANTARCTICA: Ring = Array.from({ length: 36 }, (_, i) => {
  const lon = i * 10;
  const wobble = Math.sin((lon * Math.PI) / 45) * 2.5;
  return [lon, -71 + wobble] as [number, number];
});

const CONTINENTS: Ring[] = [
  NORTH_AMERICA, SOUTH_AMERICA, AFRICA, EURASIA, AUSTRALIA, GREENLAND,
  UK_ISLES, JAPAN, MADAGASCAR, BORNEO, SUMATRA, NEW_GUINEA, NEW_ZEALAND,
  ANTARCTICA,
];

const GLOBE_RADIUS = 2;

function ContinentLines() {
  const rings = useMemo(() => CONTINENTS.map((ring) => ring.map(
    ([lon, lat]) =>
      latLonToVector3(lat, lon, GLOBE_RADIUS * 1.004).toArray() as
        [number, number, number])), []);
  return (
    <group>
      {rings.map((points, i) => (
        <Line key={i} points={points} color="#38bdf8" lineWidth={1}
          transparent opacity={0.55} depthWrite={false} />
      ))}
    </group>
  );
}

function ConnectionArcs() {
  const arcs = useMemo(() => {
    const out: Array<Array<[number, number, number]>> = [];
    for (let i = 0; i < EXCHANGES.length; i++) {
      const a = latLonToVector3(EXCHANGES[i].lat, EXCHANGES[i].lon,
        GLOBE_RADIUS * 1.004);
      const b = latLonToVector3(EXCHANGES[(i + 1) % EXCHANGES.length].lat,
        EXCHANGES[(i + 1) % EXCHANGES.length].lon, GLOBE_RADIUS * 1.004);
      const mid = a.clone().add(b).multiplyScalar(0.5).normalize()
        .multiplyScalar(GLOBE_RADIUS + a.distanceTo(b) * 0.28);
      const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
      out.push(curve.getPoints(48).map((p) => p.toArray() as
        [number, number, number]));
    }
    return out;
  }, []);
  return (
    <group>
      {arcs.map((points, i) => (
        <Line key={i} points={points} color="#7dd3fc" lineWidth={1}
          transparent opacity={0.28} depthWrite={false} />
      ))}
    </group>
  );
}

const ATMOSPHERE_VERTEX = /* glsl */ `
  varying vec3 vNormal;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix *
      vec4(position, 1.0);
  }
`;

const ATMOSPHERE_FRAGMENT = /* glsl */ `
  varying vec3 vNormal;
  void main() {
    float intensity = pow(0.62 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 3.0);
    gl_FragColor = vec4(0.16, 0.6, 1.0, 1.0) * intensity;
  }
`;

function Atmosphere() {
  return (
    <mesh scale={1.22}>
      <sphereGeometry args={[GLOBE_RADIUS, 64, 64]} />
      <shaderMaterial
        vertexShader={ATMOSPHERE_VERTEX}
        fragmentShader={ATMOSPHERE_FRAGMENT}
        blending={THREE.AdditiveBlending}
        side={THREE.BackSide}
        transparent
        depthWrite={false}
      />
    </mesh>
  );
}

function PulseRing({ marker }: { marker: ExchangeMarker }) {
  const ringRef = useRef<THREE.Mesh>(null);
  const position = useMemo(() => latLonToVector3(marker.lat, marker.lon,
    GLOBE_RADIUS * 1.011), [marker]);
  const quaternion = useMemo(() => new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 0, 1), position.clone().normalize()), [position]);

  useFrame(({ clock }) => {
    const mesh = ringRef.current;
    if (!mesh) return;
    const phase = (clock.elapsedTime % 2.4) / 2.4;
    mesh.scale.setScalar(1 + phase * 1.8);
    (mesh.material as THREE.MeshBasicMaterial).opacity = 0.45 * (1 - phase);
  });

  return (
    <group position={position} quaternion={quaternion}>
      <mesh ref={ringRef}>
        <ringGeometry args={[0.07, 0.095, 32]} />
        <meshBasicMaterial color="#38bdf8" transparent opacity={0.4}
          side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
    </group>
  );
}

function Marker({ marker }: { marker: ExchangeMarker }) {
  const setRegion = useMarketStore((s) => s.setRegion);
  const selectedRegion = useMarketStore((s) => s.region);
  const [hovered, setHovered] = useState(false);
  const position = latLonToVector3(marker.lat, marker.lon,
    GLOBE_RADIUS * 1.02);
  const isSelected = selectedRegion === marker.region;

  return (
    <mesh position={position}
      onClick={(e) => { e.stopPropagation(); setRegion(marker.region); }}
      onPointerOver={(e) => { e.stopPropagation(); setHovered(true); }}
      onPointerOut={() => setHovered(false)}>
      <sphereGeometry args={[hovered || isSelected ? 0.075 : 0.05, 16, 16]} />
      <meshStandardMaterial color={isSelected ? '#38bdf8'
        : hovered ? '#7dd3fc' : '#22c55e'}
        emissive={isSelected ? '#38bdf8' : '#14532d'}
        emissiveIntensity={isSelected ? 0.9 : 0.35} />
      {(hovered || isSelected) && (
        <Html center distanceFactor={8}>
          <div className="pointer-events-none select-none whitespace-nowrap
            rounded-md border border-sky-500/30 bg-slate-900/95 px-2 py-0.5
            text-xs font-medium text-sky-300 shadow-lg shadow-sky-500/20">
            {marker.flag} {marker.city} · {marker.region}
          </div>
        </Html>
      )}
    </mesh>
  );
}

function GlobeMesh() {
  const groupRef = useRef<THREE.Group>(null);
  const [paused, setPaused] = useState(false);
  useFrame((_state, delta) => {
    if (groupRef.current && !paused) {
      groupRef.current.rotation.y += delta * 0.1;
    }
  });
  return (
    <group ref={groupRef}
      onPointerOver={() => setPaused(true)}
      onPointerOut={() => setPaused(false)}>
      {/* Solid core */}
      <mesh>
        <sphereGeometry args={[GLOBE_RADIUS, 64, 64]} />
        <meshStandardMaterial color="#0a2540" roughness={0.65}
          metalness={0.25} />
      </mesh>
      {/* Subtle graticule */}
      <mesh>
        <sphereGeometry args={[GLOBE_RADIUS * 1.002, 36, 24]} />
        <meshBasicMaterial color="#164e63" wireframe transparent
          opacity={0.16} />
      </mesh>
      <ContinentLines />
      <ConnectionArcs />
      {EXCHANGES.map((marker) => (
        <group key={marker.region}>
          <Marker marker={marker} />
          <PulseRing marker={marker} />
        </group>
      ))}
    </group>
  );
}

export default function Globe() {
  const region = useMarketStore((s) => s.region);
  const activeExchange = EXCHANGES.find((m) => m.region === region);

  return (
    <div className="relative h-[420px] w-full overflow-hidden rounded-xl
      border border-slate-800 bg-[radial-gradient(ellipse_at_center,#0c2340_0%,#020617_75%)]"
      data-testid="globe-container">
      <Canvas camera={{ position: [0, 1.2, 6], fov: 45 }} dpr={[1, 2]}>
        <ambientLight intensity={0.5} />
        <directionalLight position={[5, 3, 5]} intensity={1.35} />
        <pointLight position={[-6, -2, -4]} intensity={0.35}
          color="#38bdf8" />
        <Stars radius={60} depth={30} count={2200} factor={3} fade />
        <Atmosphere />
        <GlobeMesh />
        <OrbitControls enablePan={false} minDistance={3.4}
          maxDistance={10} rotateSpeed={0.6} enableDamping
          dampingFactor={0.08} />
      </Canvas>
      {activeExchange && (
        <div className="absolute left-3 top-3 flex items-center gap-2
          rounded-lg border border-slate-700/60 bg-slate-900/85 px-3 py-1.5
          backdrop-blur" data-testid="globe-region-label">
          <span className="text-base leading-none">
            {activeExchange.flag}</span>
          <span className="text-xs font-semibold text-slate-200">
            {activeExchange.city}</span>
          <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[9px]
            font-bold tracking-wider text-sky-400">
            {activeExchange.region}</span>
        </div>
      )}
      <div className="absolute bottom-3 left-3 rounded-lg border
        border-slate-700/60 bg-slate-900/85 px-3 py-1.5 text-xs
        text-slate-400 backdrop-blur">
        Click a marker to filter by market · drag to rotate
      </div>
    </div>
  );
}
