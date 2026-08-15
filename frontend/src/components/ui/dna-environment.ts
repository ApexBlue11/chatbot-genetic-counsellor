import * as THREE from 'three';

/**
 * Builds a studio environment map procedurally.
 *
 * Without an environment map, `metalness` has nothing to reflect, so the
 * spheres fall back to flat diffuse shading — which is exactly what made the
 * molecule read as plain. Drei's `<Environment>` presets would fix that but
 * fetch an HDR from a CDN at runtime; this generates an equivalent gradient
 * sky plus a few soft light cards on the GPU, so the reflections cost one
 * render at mount and no network at all.
 */
export function createStudioEnvironment(renderer: THREE.WebGLRenderer): THREE.Texture {
  const scene = new THREE.Scene();

  // Gradient sky: cool light from above, deep blue below.
  const sky = new THREE.Mesh(
    new THREE.SphereGeometry(60, 32, 32),
    new THREE.ShaderMaterial({
      side: THREE.BackSide,
      uniforms: {
        top: { value: new THREE.Color('#eaf3ff') },
        middle: { value: new THREE.Color('#4d7ec7') },
        bottom: { value: new THREE.Color('#0a1836') },
      },
      vertexShader: `
        varying vec3 vPos;
        void main() {
          vPos = normalize(position);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 top; uniform vec3 middle; uniform vec3 bottom;
        varying vec3 vPos;
        void main() {
          float h = vPos.y * 0.5 + 0.5;
          vec3 c = h > 0.5
            ? mix(middle, top, smoothstep(0.5, 1.0, h))
            : mix(bottom, middle, smoothstep(0.0, 0.5, h));
          gl_FragColor = vec4(c, 1.0);
        }
      `,
    })
  );
  scene.add(sky);

  // Soft light cards — these become the highlights that travel across each
  // sphere as the molecule turns.
  const card = (
    x: number, y: number, z: number, w: number, h: number, colour: string, intensity: number
  ) => {
    const mesh = new THREE.Mesh(
      new THREE.PlaneGeometry(w, h),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(colour).multiplyScalar(intensity) })
    );
    mesh.position.set(x, y, z);
    mesh.lookAt(0, 0, 0);
    scene.add(mesh);
  };

  card(-18, 22, 14, 34, 26, '#ffffff', 3.4);   // key
  card(20, 6, -16, 26, 30, '#8fb8ff', 1.5);    // cool rim behind
  card(6, -18, 12, 30, 18, '#2f5fae', 0.9);    // bounce from below
  card(-4, 4, 30, 22, 22, '#c9dcff', 0.8);     // fill toward camera

  const pmrem = new THREE.PMREMGenerator(renderer);
  pmrem.compileEquirectangularShader();
  const target = pmrem.fromScene(scene, 0.04);

  sky.geometry.dispose();
  (sky.material as THREE.Material).dispose();
  scene.traverse((obj) => {
    if (obj instanceof THREE.Mesh && obj !== sky) {
      obj.geometry.dispose();
      (obj.material as THREE.Material).dispose();
    }
  });
  pmrem.dispose();

  return target.texture;
}
